"""
    - ONU批量升级工具v1.0说明
    - 编写人：莫凡 500264@qq.com
    - 本软件遵循GPL开源协议
    - 版本日期：20190412
    - 说明：
    1. 本程序用于OLT远程批量升级ONU，支持PON口下不同ONU混用，程序会根据不同类型ONU自动搜索匹配升级规则
    2. 目前只支持iscom5800EB OLT，程序以PON口为单位升级，如果匹配不到规则，继续匹配下一个PON口
    3. onu_rule.csv、olt_list.csv必须和程序文件放在同一目录下，且不能改名。
    4. 升级规则通过/onu_rule.csv定制。包括匹配设备类型、当前版本、ftp下载账号、密码、升级包名称等。每种设备一行，详见具体文件
    5. OLT设备ip列表放在/olt_list.txt供程序读取设备ip、telnet帐号、密码，每台OLT一行详见具体文件。
    6. 升级结果日志放在同个目录下，文件名为“result_日期_时间.csv”
    7. 程序为多进程并行升级，需根据PC性能配置决定并发进程数，数量过多会影响稳定性，ftp服务端程序需要支持高并发下载，推荐使用FileZilla server服务器程序。
    8. 命令行使用“upgrade_ISCOM5800EB.exe -p P_NUM”可实现无人值守静默升级，P_NUM为并发进程数，P_NUM必须大于等于1小于等于99。
    9. 搭配操作系统计划任务使用可实现周期自动升级。
"""

import argparse  # 接收命令行参数的库
import os
import re
import logging
from telnetlib import Telnet  # 调用telnet方法需要的库
from datetime import datetime
from multiprocessing import Pool, freeze_support
from time import sleep

# 日志模块初始化
logger = logging.getLogger()  # 定义对应的程序模块名name，默认是root
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()  # 日志输出到屏幕控制台
ch.setLevel(logging.INFO)  # 设置日志等级
home = os.getcwd()
log_filename = os.path.join(home, 'result_%s.log' % datetime.now().strftime('%Y%m%d_%H%M'))
fh = logging.FileHandler(log_filename, encoding='UTF-8')  # 向文件输出日志信息
fh.setLevel(logging.INFO)  # 设置输出到文件最低日志级别
formatter = logging.Formatter("%(asctime)s - %(message)s", '%Y-%m-%d %H:%M:%S')  # 定义日志输出格式
# 指定输出格式
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# 增加指定的handler
logger.addHandler(ch)
logger.addHandler(fh)


class Olt:
    def __init__(self, ip, telnetuser, telnetpw, rule):
        self.login_flag = False
        self.type = ''
        self.ip = ip
        self.telnetuser = telnetuser
        self.telnetpw = telnetpw
        self.rule = rule
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
        except:
            logging.warning('%s login 错误' % self.ip)

    def logout(self):
        try:
            self.tn.close()
            logging.info('%s logout 成功', self.ip)
        except:
            logging.warning('%s logout 错误', self.ip)

    # 检查OLT型号
    def check_type(self):
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
            except:
                logging.warning('%s 查询型号错误', self.ip)
        else:
            logging.warning('%s 登陆错误,查询 OLT 型号失败' % self.ip)

    # 单进程onu升级，自动判断olt类型
    def upgrade_onu(self):
        self.login()
        self.check_type()
        if self.type == 'ISCOM58EB':
            self.iscom58eb_upgrade_onu()
        else:
            logging.warning('%s 不支持的OLT类型，升级停止' % self.ip)
        self.logout()

    # 58EB单进程升级
    def iscom58eb_upgrade_onu(self):
        logging.info('%s ISCOM58EB升级开始', self.ip)
        try:
            # 遍历规则列表
            for r in self.rule:
                # 将r[1]单元格所列版本号按分隔符/切片
                oldver = r[1].split('/')
                logging.debug(oldver)
                # 遍历槽位
                slots = list(range(1, 14))
                del slots[6:8]  # 去掉主控板槽位
                for slot in slots:
                    # 遍历PON口
                    for port in range(1, 5):
                        interface = str(slot) + '/' + str(port)
                        logging.debug(interface)
                        onulist = []
                        # 读空缓存区
                        self.tn.read_very_eager()
                        cmd = 'show version onu olt %s\n' % interface
                        self.tn.write(cmd.encode())
                        # 读取ONU版本信息
                        onu_info = self.tn.read_until(b'#', timeout=2).decode("utf8", "ignore")
                        logging.debug(onu_info)
                        # 正则表达式提取ONU ID
                        oid = re.findall('ONU ID: (\S*)', onu_info)
                        # 版本列表
                        soft = re.findall('Software Version: (\S*)', onu_info)
                        # 组合成1个tuple list
                        oid_soft = zip(oid, soft)
                        # 遍历ONU版本信息表
                        for i, s in oid_soft:
                            # 遍历规则待升级版本
                            for ov in oldver:
                                # 记录待升级的ONU
                                if ov in s:
                                    logging.info('%s 待升级的ONU %s : %s', self.ip, i, s)
                                    # 将x/x/x的全局ID截取成单PON口下的短ID
                                    llid = i[len(interface) + 1:]
                                    onulist.append(llid)
                        # 组合成待升级的ONU字串
                        onu = interface + '/' + ','.join(onulist)
                        # 待升级列表非空
                        if onulist:
                            cmd = 'download slave-system-boot ftp %s %s %s %s onu %s commit\n' % (
                                r[3], r[4], r[5], r[6], onu)
                            logging.info('%s ' + cmd, self.ip)
                            res1 = self.tn.read_very_eager().decode('utf8', 'ignore')
                            logging.debug(res1)
                            # 开始download
                            self.tn.write(cmd.encode())
                            sleep(3)
                            self.tn.write('yes\n'.encode())
                            res2 = self.tn.expect([b'[Ss]uccess.*', b'[Ff]ail.*', b'[Ff]inish.*'], timeout=590)
                            result = res2[2].decode('utf8', 'ignore')
                            logging.info('%s interface olt %s 升级结果 :\n%s', self.ip, interface, result)
                            # 重启onu
                            cmd = 'reboot onu %s now\n' % onu
                            self.tn.write(cmd.encode())
                            logging.info('%s ' + cmd, self.ip)
                        else:
                            logging.info('%s %s : ONU无需升级', self.ip, interface)
            logging.info('%s ISCOM58EB升级完成', self.ip)
        except:
            logging.info('%s ISCOM58EB升级异常', self.ip)


def multiprocess_upgrade(p_num):
    # 获取当前工作目录
    cwd = os.getcwd()
    # 生成规则文件路径
    f1 = os.path.join(cwd, 'onu_rule.csv')
    rule = []
    # 尝试读取规则文件
    try:
        with open(f1, mode='r') as f:
            # 从文件中逐行取出规则，放到二维矩阵rule[]中
            for line in f:
                rule.append(line.split(','))
    # 规则文件读取错误处理
    except:
        logging.error('错误，升级规则文件%s不存在或路径错误' % f1)
        exit()
    # 剔除首行抬头说明行
    rule.pop(0)
    # 校验每行升级规则是否符合规范
    for r in rule:
        index = rule.index(r) + 2
        # 必填字段缺失错误处理
        if '' in r[1:7]:
            logging.error('错误！升级规则表第%d行中必填字段未填写！' % index)
            exit()

    # 生成ip列表文件路径
    f2 = os.path.join(cwd, 'olt_list.csv')
    # 尝试读取olt列表文件，放入二维矩阵ip_list[]。
    ip_list = []
    try:
        with open(f2, mode='r') as f:
            for line in f:
                ip_list.append(line.split(','))
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

    # 创建进程池，个数根据PC处理能力适当选择
    p = Pool(p_num)
    # 开启多进程异步升级，回调函数记录结果到log文件
    for i in ip_list:
        ip = i[0]
        telnetuser = i[1]
        telnetpw = i[2]
        my_olt = Olt(ip, telnetuser, telnetpw, rule)
        p.apply_async(my_olt.upgrade_onu)
    p.close()
    p.join()
    logging.info('批量升级执行完成')


if __name__ == '__main__':
    # windows的可执行文件，必须添加支持程序冻结，该命令需要在__main__函数下
    freeze_support()

    # 交互界面开始
    print('''
    - ONU批量升级工具v1.0说明
    - 编写人：莫凡 500264@qq.com
    - 本软件遵循GPL开源协议
    - 版本日期：20190412
    - 说明：
    1. 本程序用于OLT远程批量升级ONU，支持PON口下不同ONU混用，程序会根据不同类型ONU自动搜索匹配升级规则
    2. 目前只支持iscom5800EB OLT，程序以PON口为单位升级，如果匹配不到规则，继续匹配下一个PON口
    3. onu_rule.csv、olt_list.csv必须和程序文件放在同一目录下，且不能改名。
    4. 升级规则通过/onu_rule.csv定制。包括匹配设备类型、当前版本、ftp下载账号、密码、升级包名称等。每种设备一行，详见具体文件
    5. OLT设备ip列表放在/olt_list.txt供程序读取设备ip、telnet帐号、密码，每台OLT一行详见具体文件。
    6. 升级结果日志放在同个目录下，文件名为“result_日期_时间.csv”
    7. 程序为多进程并行升级，需根据PC性能配置决定并发进程数，数量过多会影响稳定性，ftp服务端程序需要支持高并发下载，推荐使用FileZilla server服务器程序。
    8. 命令行使用“upgrade_ISCOM5800EB.exe -p P_NUM”可实现无人值守静默升级，P_NUM为并发进程数，P_NUM必须大于等于1小于等于99。
    9. 搭配操作系统计划任务使用可实现周期自动升级。
    ''')
    # 实例化参数解析器
    parser = argparse.ArgumentParser()
    # 增加命令行选项-p
    parser.add_argument("-p", "--p_num", type=int, choices=range(1, 100))
    # 解析命令行参数到args类
    args = parser.parse_args()
    # 命令行加-p选项，无人值守静默升级
    if args.p_num is not None:
        print("进行无人值守静默升级，并发进程数为：", args.p_num)
        multiprocess_upgrade(args.p_num)
    # 如果命令行不加-p选项，进行交互式升级
    else:
        while True:
            # 接收控制台输入，input方法获取的是字符串，需要转成整数
            p_unm = int(input('请输入并发进程数，根据PC处理能力适当选择，推荐为CPU数量的整数倍：'))
            if 0 < p_unm < 100:
                break
            print("非法数值，请从新输入1到99之间的整数")
        multiprocess_upgrade(p_unm)
        input('升级完成，升级结果日志放在本目录下，文件名为“result_日期_时间.csv”，按回车退出')
