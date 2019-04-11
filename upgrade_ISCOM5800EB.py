'''
- ISCOM5800EB批量升级工具v0.1
- 编写人：莫凡 500264@qq.com
- 版本日期：20190325
- 说明：
1. 本脚本用于EPON ONU的自动一键升级，用户不需检查待升级设备类型，脚本会自动搜索匹配升级规则，如果匹配不到规则，会报错并继续匹配下一台;
2. 升级规则通过/upgrade_rule.csv定制。包括匹配设备类型、硬件版本、指定目标bootrom版本和文件、指定目标system版本和文件、是否备份配置、ftp下载账号、是否重启激活等。每种设备一行，详见具体文件。
3. upgrade_rule.csv、u_ip_list.txt必须和程序文件放在同一目录下，且不能改名。
5. 升级设备ip列表放在/u_ip_list.txt供程序读取设备ip，每行一条ip
6. 升级结果日志放在/result子目录下，文件名为“日期_时间.csv”，如果/result目录不存在，自动创建
7. 程序为多进程并行升级，需根据PC性能配置决定并发进程数，数量过多会影响稳定性，ftp服务端程序需要支持高并发下载，推荐使用FileZilla server服务器程序。
'''

import argparse  # 接收命令行参数的库
import os
import re
import logging
import telnetlib  # 调用telnet方法需要的库
from datetime import datetime
from multiprocessing import Pool, freeze_support
from time import sleep

logger = logging.getLogger()  # 定义对应的程序模块名name，默认是root
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()  # 日志输出到屏幕控制台
ch.setLevel(logging.INFO)  # 设置日志等级
home = os.getcwd()
log_filename = os.path.join(home, 'result_%s.log' % datetime.now().strftime('%Y%m%d_%H%M%S'))
# log_filename='d:/result_%s.log' %datetime.now().strftime('%Y%m%d_%H%M%S')
fh = logging.FileHandler(log_filename)  # 向文件输出日志信息
fh.setLevel(logging.INFO)  # 设置输出到文件最低日志级别
formatter = logging.Formatter("%(asctime)s - PID:%(process)d - %(message)s", '%Y-%m-%d %H:%M:%S')  # 定义日志输出格式
# 指定输出格式
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# 增加指定的handler
logger.addHandler(ch)
logger.addHandler(fh)


class olt():
    def __init__(self, ip, telnetuser, telnetpw, rule):
        self.ip = ip
        self.telnetuser = telnetuser
        self.telnetpw = telnetpw
        self.rule = rule

    def login(self):
        try:
            self.tn = telnetlib.Telnet(self.ip.encode(), port=23, timeout=3)
            # 登陆交互
            self.tn.write(b'\n')
            self.tn.read_until(b'Login:', timeout=2)
            self.tn.write(self.telnetuser.encode() + b'\n')
            self.tn.read_until(b'Password:', timeout=2)
            self.tn.write(self.telnetpw.encode() + b'\n')
            self.tn.read_until(b'>', timeout=2)
            self.tn.write('enable\n'.encode())
            self.tn.read_until(b'Password:', timeout=2)
            self.tn.write('raisecom\n'.encode())
            if '#' in self.tn.read_until(b'#', timeout=2).decode("utf8", "ignore"):
                self.login_flag = True
            else:
                self.login_flag = False
        except:
            logging.warning('login error')
            self.login_flag = False

    def logout(self):
        try:
            self.tn.close()
            logging.info('logout from %s successfully', self.ip)
        except:
            logging.warning('logout from %s error', self.ip)

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
                else:
                    self.type = 'other'
                logging.debug('%s OLT type is %s', self.ip, self.type)
            except:
                logging.warning('check OLT type error')
                self.type = 'error'
        else:
            logging.warning('did not login,check OLT type error')
            self.type = 'error'

    # 单进程onu升级，自动判断olt类型
    def upgrade_onu(self):
        if self.type == 'ISCOM58EB':
            self.ISCOM58EB_upgrade_onu()
        else:
            logging.warning('不支持的OLT类型，升级停止')

    # 58EB单进程升级
    def ISCOM58EB_upgrade_onu(self):
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
                            logging.debug(self.tn.read_very_eager().decode('utf8', 'ignore'))
                            # 开始download
                            self.tn.write(cmd.encode())
                            sleep(3)
                            self.tn.write('yes\n'.encode())
                            result = self.tn.read_until(b'#', timeout=590).decode("utf8", "ignore")
                            logging.info('%s interface olt %s download result :\n%s', self.ip, interface, result)
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
    home = os.getcwd()
    # 生成规则文件路径
    f1 = os.path.join(home, 'upgrade_rule.csv')
    rule = []
    # 尝试读取规则文件
    try:
        # 从文件中逐行取出规则，放到二维矩阵rule[]中
        with open(f1, mode='r') as f:
            for line in f:
                rule.append(line.split(','))
    # 规则文件读取错误处理
    except:
        print('错误，升级规则文件%s不存在或路径错误' % f1)
        exit()
    # 剔除首行抬头说明行
    rule.pop(0)
    # 校验每行升级规则是否符合规范
    for r in rule:
        index = rule.index(r) + 2
        # 必填字段缺失错误处理
        if r[0] == '' or r[1] == '' or r[3] == '' or r[5] == '':
            print('错误！升级规则表第%d行中必填字段未填写！' % index)
            exit()
        # bootrom镜像文件缺失错误处理
        if r[2] != '' and r[4] == '':
            print('错误！升级规则表第%d行中定义了bootrom目标版本，未定义bootrom升级文件' % index)
            exit()

    # 生成ip列表文件路径
    f2 = os.path.join(home, 'u_ip_list.txt')
    # 尝试读取设备ip列表文件，放入ip_list列表。
    try:
        with open(f2, 'r') as f:
            ip_list = f.read().split()  # 读取的文件切片成设备列表
        while '' in ip_list:
            ip_list.remove('')  # 移除列表中的空行
    # ip列表文件读取错误处理
    except:
        print('错误，设备列表文件名%s不存在或路径不对' % f2)
        exit()

    # 创建进程池，个数根据PC处理能力适当选择
    p = Pool(p_num)
    # 开启多进程异步升级，回调函数记录结果到log文件
    for ip in ip_list:
        p.apply_async(itn185_331_download_system, args=(ip, rule,), callback=log.write)
    p.close()
    p.join()
    log.close()
    end_time = datetime.now()
    print(end_time, '批量升级执行完成，共耗时', end_time - start_time)


if __name__ == '__main__':
    # windows的可执行文件，必须添加支持程序冻结，该命令需要在__main__函数下
    freeze_support()
    print('''
    - ITN185_331批量升级工具v1.2说明
    - 编写人：莫凡 500264@qq.com
    - 鸣谢：冀文超 提供源代码思路
    - 版本日期：20190325
    - 说明：
    1. 本程序用于台式IPRAN设备的自动一键升级，用户不需检查待升级设备类型，程序会自动搜索匹配升级规则，如果匹配不到规则，会报错并继续匹配下一台;
    2. 升级规则通过/upgrade_rule.csv定制。包括匹配设备类型、硬件版本、指定目标bootrom版本和文件、指定目标system版本和文件、是否备份配置、ftp下载账号、是否重启激活等。每种设备一行，详见具体文件。
    3. upgrade_rule.csv、u_ip_list.txt必须和程序文件放在同一目录下，且不能改名。
    4. 升级时一定要保证itn设备FLASH内存空间足够，否则异常！
    5. 升级设备ip列表放在/u_ip_list.txt供程序读取设备ip，每行一条ip
    6. 升级结果日志放在/result子目录下，文件名为“日期_时间.csv”，如果/result目录不存在，自动创建
    7. 程序为多进程并行升级，需根据PC性能配置决定并发进程数，数量过多会影响稳定性，ftp服务端程序需要支持高并发下载，推荐使用FileZilla server服务器程序。
    8. 升级规则可以指定升级前、升级成功后擦除旧版本文件，当然新版本文件名不能用同样的名字，否则会被误擦除！
    9. 目前不支持paf文件升级
    10. 命令行使用“upgrade_iTN185_331_multiprocess.exe -p P_NUM”可实现无人值守静默升级，P_NUM为并发进程数，P_NUM必须大于等于1小于等于99。
    ''')
    # 实例化参数解析器
    parser = argparse.ArgumentParser()
    # 增加命令行选项-p
    parser.add_argument("-p", "--p_num", type=int, choices=range(1, 100))
    # 解析命令行参数到args类
    args = parser.parse_args()
    # 命令行加-p选项，无人值守静默升级
    if args.p_num != None:
        print("进行无人值守静默升级，并发进程数为：", args.p_num)
        multiprocess_upgrade(args.p_num)
    # 如果命令行不加-p选项，进行交互式升级
    else:
        while True:
            # 接收控制台输入，input方法获取的是字符串，需要转成整数
            pool = int(input('请输入并发进程数，根据PC处理能力适当选择，推荐为CPU数量的整数倍：'))
            if 0 < pool < 100:
                break
            print("非法数值，请从新输入1到99之间的整数")
        multiprocess_upgrade(pool)
        input('升级完成，升级结果日志放在/result子目录下，文件名为“日期_时间.csv”，按回车退出')
