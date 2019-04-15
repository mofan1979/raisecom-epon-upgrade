- ONU批量升级工具v1.0说明
- 编写人：莫凡 500264@qq.com
- 本软件遵循GPL开源协议
- 版本日期：20190415
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
10. 如果windows环境运行提示缺少API-MS-Win-Core-Console-L1-1-0.dll运行库，请下载安装[微软常用运行库合集](http://baoku.360.cn/soft/show/appid/104698064)