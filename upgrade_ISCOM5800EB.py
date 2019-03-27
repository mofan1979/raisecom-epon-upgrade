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
import telnetlib  # 调用telnet方法需要的库
from datetime import datetime
from multiprocessing import Pool, freeze_support
from time import sleep


def onu_upgrade(ip, telnetuser,telnetpw,rule):
    # 定义执行升级函数，需要传入参数为设备ip，telnet帐号密码，规则列表矩阵
    # 尝试发起telnet连接
    t01 = datetime.now()
    try:
        tn = telnetlib.Telnet(ip.encode(), port=23, timeout=3)
        # 登陆交互
        tn.write(b'\n')
        tn.read_until(b'Login:')
        tn.write(telnetuser.encode()+b'\n')
        tn.read_until(b'Password:')
        tn.write(telnetpw.encode()+b'\n')
        tn.read_until(b'>')
        tn.write('enable\n'.encode())
        tn.read_until(b'Password:')
        tn.write('raisecom\n'.encode())
        tn.read_until(b'#')

        # 读取ONU版本
        tn.write('show version onu slot 1-13\n'.encode())
        # 解码成Unicode格式以供比对
        devinfo = tn.read_until(b'#').decode()
        # print(devinfo)
        # 逐行比对升级规则
        for r in rule:
            ftp_host = r[9]
            ftp_user = r[10]
            ftp_pw = r[11]
            if devinfo.find('Product Name: %s' % r[0]) >= 0 and devinfo.find('Hardware Version: %s' % r[1]) >= 0:
                # 匹配设备型号和硬件版本成功
                devtype = r[0] + ':' + r[1]
                print(ip, '升级的设备类型是', devtype)
                # print(devinfo.find(r[3]))
                if devinfo.find(r[3]) >= 0:
                    print(ip, '恭喜，设备system版本已经是最新，无需升级')
                    return '%s,成功,无需升级\n' % ip
                # 下载升级包
                try:
                    # 记录开始时间
                    t0 = datetime.now()
                    # 备份startup配置
                    if r[8] == 'yes':
                        cmd_line = 'write\n'
                        print('[', t0, ']', ip, devtype, '执行', cmd_line)
                        tn.write(cmd_line.encode())
                        tn.read_until(b'#')
                        ft0 = t0.strftime('%Y%m%d_%H%M%S')
                        cmd_line = 'upload startup-config ftp %s %s %s %s-%s.conf\n' % (
                            ftp_host, ftp_user, ftp_pw, ip, ft0)
                        print('[', datetime.now(), ']', ip, devtype, '执行', cmd_line)
                        tn.write(cmd_line.encode())
                        flag = tn.read_until(b'#').decode().find(' success')
                        # 备份不成功则报错退出，成功则继续
                        if flag < 0:
                            # 确认telnet会话是否存活
                            try:
                                tn.close()
                                print('[', datetime.now(), ']', '%s,失败,备份startup-config失败' % ip)
                                return '%s,失败,备份startup-config失败\n' % ip
                            except:
                                print('[', datetime.now(), ']', '%s,失败,备份startup-config过程中telnet连接中断' % ip)
                                return '%s,失败,telnet连接中断\n' % ip
                        print('[', datetime.now(), ']', ip, devtype, '备份startup-config成功')
                    # 清理前次升级失败冗余的镜像文件
                    if r[6] != '':
                        tn.write('dir\n'.encode())  # 显示flash文件列表
                        flag = tn.read_until(b'#').decode().find(r[6])
                        # print(flag)
                        if flag >= 0:
                            t60 = datetime.now()
                            cmd_line = 'erase flash/core/%s\n' % r[6]
                            print('[', t60, ']', ip, devtype, '执行', cmd_line)
                            tn.write(cmd_line.encode())
                            tmp = tn.read_until(b"Please input 'yes' to confirm:").decode()
                            # print(tmp)
                            cmd_line1 = 'yes\n'
                            tn.write(cmd_line1.encode())
                            # print(cmd_line1)
                            result = tn.read_until(b'#', timeout=600).decode()
                            print(result.find(' success'))
                            t61 = datetime.now()
                            if result.find(' success') >= 0:
                                print('[', t61, ']', ip, devtype, cmd_line, '执行成功，耗时：', t61 - t60)
                            else:
                                print('[', t61, ']', ip, devtype, cmd_line, '执行失败，耗时：', t61 - t60)
                                # return  '%s,失败,%s出错\n' % ip %cmd_line
                                # 此处失败不影响后续操作
                    # 下面开始判断升级bootrom
                    t2 = datetime.now()
                    if r[2] != '' and devinfo.find('Bootrom Version: %s' % r[2]) < 0:
                        cmd_line = 'download bootstrap ftp %s %s %s %s\n' % (ftp_host, ftp_user, ftp_pw, r[4])
                        print('[', t2, ']', ip, devtype, '执行', cmd_line)
                        tn.write(cmd_line.encode())
                        result1 = tn.read_until(b'#', timeout=180).decode()  # 获取bootrom升级结果
                        # print(result1)
                        t3 = datetime.now()
                        if result1.find(' success') >= 0:
                            print('[', t3, ']', ip, devtype, 'BOOTROM下载成功，共耗时 ', t3 - t2)
                        # bootrom升级失败则报错退出
                        else:
                            # 判断telnet会话存活
                            try:
                                tn.close()
                                print('[', t3, ']', ip, devtype, 'BOOTROM升级异常或超时，共耗时 ', t3 - t2)
                                return '%s,失败,下载bootrom出错\n' % ip
                            except:
                                print('[', datetime.now(), ']', '%s,失败,bootrom升级过程中telnet连接中断' % ip)
                                return '%s,失败,telnet连接中断\n' % ip
                    # 下面开始升级system
                    tn.write('dir\n'.encode())
                    dirlist = tn.read_until(b'#').decode()
                    flag = dirlist.find(r[5])  # 判断是否有已存在的文件，为后面二次确认做准备
                    # print(flag)
                    cmd_line = 'download system ftp %s %s %s %s\n' % (ftp_host, ftp_user, ftp_pw, r[5])
                    t4 = datetime.now()
                    print('[', t4, ']', ip, devtype, 'bootrom版本满足，开始执行', cmd_line)
                    tn.write(cmd_line.encode())
                    # 如果已经有存在的文件，确认覆盖升级
                    if flag >= 0:
                        sleep(3)
                        tn.write('yes\n'.encode())  # 等待3秒后输入yes二次确认
                    # 获取命令结果
                    result1 = tn.read_until(b'#', timeout=2700).decode()
                    # print(result1)
                    t5 = datetime.now()
                    # 判断返回，如果含有download system success，则成功，超时抛出失败
                    if result1.find(' success') >= 0:  # 注意success前有空格，以便区分unsuccessful和successful
                        # 指定启动文件
                        cmd_line = 'boot next-startup %s \n' % r[5]
                        print('[', t5, ']', ip, devtype, 'system下载成功，耗时', t5 - t4, '，正在执行', cmd_line)
                        tn.write(cmd_line.encode())
                        result3 = tn.read_until(b'#', timeout=300).decode()
                        t6 = datetime.now()
                        # 判断boot next-startup是否成功
                        if result3.find(' success') >= 0:
                            print('[', t6, ']', ip, devtype, cmd_line, '执行成功，耗时', t6 - t5)
                            # 判断是否需要擦除旧的镜像文件
                            if r[7] != '':
                                # 将r[7]单元格所列文件名按分隔符/切片
                                eraselist = r[7].split('/')
                                # 迭代比较列表中文件名
                                for e in eraselist:
                                    # 假如存在该文件名则擦除
                                    if dirlist.find(e) >= 0:
                                        t6 = datetime.now()
                                        cmd_line = 'erase flash/core/%s\n' % e
                                        print('[', t6, ']', ip, devtype, '执行', cmd_line)
                                        tn.write(cmd_line.encode())
                                        sleep(2)
                                        cmd_line2 = 'yes\n'
                                        tn.write(cmd_line2.encode())
                                        # print(cmd_line)
                                        tmp = tn.read_until(b'#').decode()
                                        # print(tmp)
                                        t7 = datetime.now()
                                        # 此处擦除成功与否不影响升级结果
                                        if tmp.find(' success') >= 0:
                                            print('[', t7, ']', ip, devtype, '执行', cmd_line, '成功，耗时：', t7 - t6)
                                        else:
                                            print('[', t7, ']', ip, devtype, '执行', cmd_line, '失败，耗时：', t7 - t6)
                            # 判断是否需要重启激活，只有填写yes才重启，其他值均不重启。注意r[12]作为行尾带有换行符'\n'
                            if r[12].find('yes') >= 0:
                                cmd_line = 'write\n'
                                tn.write(cmd_line.encode())
                                tn.read_until(b'#')
                                cmd_line = 'reboot now\n'
                                print('[', datetime.now(), ']', ip, devtype, '执行', cmd_line)
                                tn.write(cmd_line.encode())
                                return '%s,成功,升级systemboot成功，并重启激活\n' % ip
                            # 如果不需要重启激活
                            else:
                                # 判断telnet会话存活
                                try:
                                    tn.close()
                                    print('[', t6, ']', ip, devtype, '等待重启激活')
                                    return '%s,成功,升级systemboot成功，等待重启激活\n' % ip
                                except:
                                    print('[', datetime.now(), ']', '%s,失败,指定启动文件过程中telnet连接中断' % ip)
                                    return '%s,失败,telnet连接中断\n' % ip
                        # boot next-startup执行错误处理
                        else:
                            # 判断telnet会话存活
                            try:
                                tn.close()
                                print('[', t6, ']', ip, devtype, '执行', cmd_line, '失败，耗时', t6 - t5)
                                return '%s,失败,指定boot next-startup文件失败\n' % ip
                            except:
                                print('[', datetime.now(), ']', '%s,失败,指定启动文件过程中telnet连接中断' % ip)
                                return '%s,失败,telnet连接中断\n' % ip
                    # 如果system下载失败
                    else:
                        try:
                            # 确认telnet会话是否存活
                            tn.close()
                            print('[', t5, ']', ip, devtype, cmd_line, '执行异常或超时，耗时 ', t5 - t4)
                            return '%s,失败,下载system出错\n' % ip
                        except:
                            print('[', t5, ']', ip, devtype, '升级system过程telnet连接中断，耗时 ', t5 - t4)
                            return '%s,失败,telnet连接中断\n' % ip
                # 升级过程异常处理
                except:
                    t8 = datetime.now()
                    try:
                        # 确认telnet会话是否存活
                        tn.close()
                        print('[', t8, ']', ip, devtype, '升级异常，其他未知原因，共耗时 ', t8 - t0)
                        return '%s,失败,其他未知原因\n' % ip
                    except:
                        print('[', t8, ']', ip, devtype, '升级异常，telnet连接中断，共耗时 ', t8 - t0)
                        return '%s,失败,telnet连接中断\n' % ip
        # 遍历规则无匹配的处理
        t91 = datetime.now()
        try:
            # 确认telnet会话是否存活
            tn.close()
            print('%s，失败，不支持的设备类型' % ip)
            return '%s,失败,不支持的设备类型\n' % ip
        except:
            print('[', t91, ']', ip, '比对型号版本过程异常，telnet连接中断，共耗时 ', t91 - t01)
            return '%s,失败,telnet连接中断\n' % ip
    # telnet异常错误处理
    except:
        print('%s telnet连接失败，非RC设备或设备离线' % ip)
        return '%s,失败,非RC设备或设备离线\n' % ip


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

    # 结果日志保存目录，如没有，则创建
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
        print('错误，结果日志文件存放路径/result不存在')
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
