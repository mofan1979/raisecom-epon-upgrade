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