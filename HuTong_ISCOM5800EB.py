"""
- OLT解耦信息采集工具v1.0说明
- 编写人：莫凡 500264@qq.com
- 本软件遵循GPL协议
- 版本日期：20190424
- 说明：
1. 本程序用于OLT巡检，记录软件版本、mac、当前日期信息
2. 程序入口batch_check()，目前只支持iscom5800EB OLT
3. olt_list.csv必须和程序文件放在同一目录下，且不能改名。
4. OLT设备ip列表放在/olt_list.csv供程序读取设备ip、telnet帐号、密码，每台OLT一行详见具体文件。
5. 采集结果放在/result目录下，文件名为“result_日期_时间.csv”

- OLT解耦配置工具v1.0说明
- 编写人：莫凡 500264@qq.com
- 本软件遵循GPL协议
- 版本日期：20190424
- 说明：
1. 本程序用于OLT解耦，异厂家互通
2. 程序入口batch_hutong()，目前只支持iscom5800EB OLT
3. HuTong_olt.csv必须和程序文件放在同一目录下，且不能改名。
4. OLT设备ip列表放在/HuTong_olt.csv供程序读取设备ip、帐号、密码，每台OLT一行详见具体文件。
5. 解耦结果日志放在/result目录下，文件名为“result_日期_时间.csv”
"""

import os
import re
import logging
from telnetlib import Telnet  # 调用telnet方法需要的库
from datetime import datetime
# 用第三方库解决多进程读写日志文件安全问题
from concurrent_log_handler import ConcurrentRotatingFileHandler

# 日志模块初始化
logger = logging.getLogger()  # 定义对应的程序模块名name，默认是root
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()  # 日志输出到屏幕控制台
ch.setLevel(logging.INFO)  # 设置日志等级
home = os.getcwd()
log_filename = os.path.join(home, 'result_%s.log' % datetime.now().strftime('%Y%m%d_%H%M'))
fh = ConcurrentRotatingFileHandler(log_filename, encoding='utf-8')  # 向文件输出日志信息
fh.setLevel(logging.INFO)  # 设置输出到文件最低日志级别
formatter = logging.Formatter("%(asctime)s - %(message)s\r\n", '%Y-%m-%d %H:%M:%S')  # 定义日志输出格式
# 指定输出格式
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# 增加指定的handler
logger.addHandler(ch)
logger.addHandler(fh)


class Olt:
    def __init__(self, ip, telnetuser, telnetpw):
        self.login_flag = False
        self.type = ''
        self.ip = ip
        self.telnetuser = telnetuser
        self.telnetpw = telnetpw
        self.tn = Telnet()

    def login(self):
        try:
            self.tn.open(self.ip.encode(), port=23, timeout=3)
            # 登陆交互
            self.tn.write(b'\n')
            self.tn.expect([b'[Ll]ogin:'], timeout=2)
            self.tn.write(self.telnetuser.encode() + b'\n')
            self.tn.read_until(b'Password:', timeout=2)
            self.tn.write(self.telnetpw.encode() + b'\n')
            self.tn.read_until(b'>', timeout=2)
            self.tn.write('enable\n'.encode())
            self.tn.read_until(b'Password:', timeout=2)
            self.tn.write('raisecom\n'.encode())
            if '#' in self.tn.read_until(b'#', timeout=2).decode("utf8", "ignore"):
                self.login_flag = True
                logging.info('%s login 成功', self.ip)
            else:
                logging.warning('%s login 失败，非raisecom设备或密码错误' % self.ip)
                self.logout()
                return '%s,login 失败，非raisecom设备或密码错误\n' % self.ip
        except:
            logging.warning('%s login 失败，设备不在线' % self.ip)
            return '%s,login 失败，设备不在线\n' % self.ip

    def logout(self):
        try:
            self.tn.close()
            logging.info('%s logout 成功', self.ip)
        except:
            logging.warning('%s logout 错误', self.ip)

    # 检查OLT型号
    def check_type(self):
        login_res = self.login()
        if self.login_flag:
            try:
                # 关闭日志打印以防干扰
                self.tn.write('config\n'.encode())
                self.tn.read_until(b"#", timeout=2)
                self.tn.write('no logging monitor\n'.encode())
                self.tn.read_until(b"#", timeout=2)
                self.tn.write('end\n'.encode())
                self.tn.read_until(b"#", timeout=2)
                # 读取OLT版本
                self.tn.write('show version\n'.encode())
                oltinfo = self.tn.read_until(b"#", timeout=2).decode("utf8", "ignore")
                if 'ISCOM5800E-SMCB' in oltinfo:
                    self.type = 'ISCOM58EB'
                logging.debug('%s OLT 型号为 %s', self.ip, self.type)
                ver = ''.join(re.findall('Software Version: (.*)\(Compiled', oltinfo))
                mac = ' '.join(re.findall('System MAC Address: (\w\w)(\w\w)\.(\w\w)(\w\w)\.(\w\w)(\w\w)', oltinfo)[0])
                self.tn.write('show clock\n'.encode())
                systime = self.tn.read_until(b"#", timeout=2).decode("utf8", "ignore")
                date = ''.join(re.findall('Current system time\(d\): (.*)\r', systime))
                logging.info('%s,%s,%s,%s' % (self.ip, ver, mac, date))
                self.logout()
                return '%s,%s,%s,%s\n' % (self.ip, ver, mac, date)
            except:
                logging.warning('%s 查询型号错误', self.ip)
                self.logout()
                return '%s,查询型号错误\n' % self.ip
        return login_res


class HutongOlt(Olt):
    def __init__(self, ip, telnetuser, telnetpw, debugpw):
        super().__init__(ip, telnetuser, telnetpw)
        self.debugpw = debugpw

    # 开互通
    def hutong(self):
        login_res = self.login()
        if self.login_flag:
            try:
                # 关闭日志打印以防干扰
                self.tn.write('config\n'.encode())
                self.tn.read_until(b"#", timeout=2)
                self.tn.write('no logging monitor\n'.encode())
                self.tn.read_until(b"#", timeout=2)
                self.tn.write('end\n'.encode())
                self.tn.read_until(b"#", timeout=2)
                # 进入隐藏debug模式
                self.tn.write('debug-hide\n'.encode())
                self.tn.read_until(b'Password:', timeout=1)
                self.tn.write(self.debugpw.encode() + b'\n')
                if '(debug)' not in self.tn.read_until(b"#", timeout=2).decode('utf8', 'ignore'):
                    logging.warning('%s 解耦密码错误' % self.ip)
                    self.logout()
                    return '%s,解耦密码错误\n' % self.ip
                self.tn.write('non-rc-onu handling register\n'.encode())
                res = self.tn.read_until(b"#", timeout=2).decode('utf8', 'ignore')
                if ' success' not in res:
                    logging.warning('%s 解耦命令执行失败，请登陆查询具体原因' % self.ip)
                    self.logout()
                    return '%s 解耦命令执行失败，请登陆查询具体原因\n' % self.ip
                logging.info('%s 解耦命令执行结果为：\n%s' % (self.ip, res))
                self.tn.write('end\n'.encode())
                self.tn.read_until(b'#', timeout=1)
                self.tn.write('write\n'.encode())
                if ' success' not in self.tn.read_until(b'#', timeout=30).decode('utf8', 'ignore'):
                    logging.warning('%s 解耦成功，保存失败，请手动保存' % self.ip)
                    self.logout()
                    return '%s,解耦成功，保存失败，请手动保存\n' % self.ip
                logging.warning('%s 解耦成功' % self.ip)
                self.logout()
                return '%s,解耦成功\n' % self.ip
            except:
                logging.warning('%s 解耦操作异常中断', self.ip)
                self.logout()
                return '%s,解耦操作异常中断\n' % self.ip
        return login_res


def batch_check():
    # 获取当前工作目录
    cwd = os.getcwd()
    # 生成ip列表文件路径
    f2 = os.path.join(cwd, 'olt_list.csv')
    # 尝试读取olt列表文件，放入二维矩阵ip_list[]。
    try:
        with open(f2, mode='r') as f:
            temp = []
            for line in f:
                ls = line.strip('\n')
                # 去重处理
                if ls not in temp:
                    temp.append(ls)
        ip_list = []
        for item in temp:
            ip_list.append(item.split(','))
    # ip列表文件读取错误处理
    except:
        logging.error('错误，设备列表文件%s不存在或路径不对' % f2)
        exit()
    # 剔除首行抬头说明行
    ip_list.pop(0)
    for i in ip_list:
        index = ip_list.index(i) + 2
        # 必填字段缺失错误处理
        if '' in i:
            logging.error('错误！设备列表第%d行中必填字段未填写！' % index)
            exit()

    f3 = os.path.join(home, 'result')
    if not os.path.exists(f3):
        os.makedirs(f3)
    start_time = datetime.now()
    # 结果日志存放路径，文件名为格式化日期_时间.csv
    logfile = os.path.join(f3, '%s.csv') % start_time.strftime('%Y%m%d_%H%M%S')
    try:
        log = open(logfile, mode='a')
    # 日志文件操作错误处理
    except:
        logging.error('错误，结果日志文件存放路径/result不存在')
        exit()

    for i in ip_list:
        ip = i[0]
        telnetuser = i[1]
        telnetpw = i[2]
        my_olt = Olt(ip, telnetuser, telnetpw)
        res = my_olt.check_type()
        log.write(res)
    logging.info('批量执行完成')


def batch_hutong():
    # 获取当前工作目录
    cwd = os.getcwd()

    # 生成ip列表文件路径
    f2 = os.path.join(cwd, 'HuTong_olt.csv')
    # 尝试读取olt列表文件，放入二维矩阵ip_list[]。
    try:
        with open(f2, mode='r') as f:
            temp = []
            for line in f:
                ls = line.strip('\n')
                # 去重处理
                if ls not in temp:
                    temp.append(ls)
        ip_list = []
        for item in temp:
            ip_list.append(item.split(','))
    # ip列表文件读取错误处理
    except:
        logging.error('错误，设备列表文件%s不存在或路径不对' % f2)
        exit()
    # 剔除首行抬头说明行
    ip_list.pop(0)
    # for i in ip_list:
    #     index = ip_list.index(i) + 2
    #     # 必填字段缺失错误处理
    #     if '' in i:
    #         logging.error('错误！设备列表第%d行中必填字段未填写！' % index)
    #         exit()

    f3 = os.path.join(home, 'result')
    if not os.path.exists(f3):
        os.makedirs(f3)
    start_time = datetime.now()
    # 结果日志存放路径，文件名为格式化日期_时间.csv
    logfile = os.path.join(f3, '%s.csv') % start_time.strftime('%Y%m%d_%H%M%S')
    try:
        log = open(logfile, mode='a')
    # 日志文件操作错误处理
    except:
        logging.error('错误，结果日志文件存放路径/result不存在')
        exit()

    for i in ip_list:
        ip = i[0]
        telnetuser = i[1]
        telnetpw = i[2]
        debugpw = i[3]
        my_olt = HutongOlt(ip, telnetuser, telnetpw, debugpw)
        res = my_olt.hutong()
        log.write(res)
        log.flush()
    log.close()
    logging.info('批量执行完成')


if __name__ == '__main__':
    batch_hutong()
    # batch_check()
