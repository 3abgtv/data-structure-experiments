"""任务调度模拟器 —— 源码包。

分层（对应任务书要求的模块划分）：

    models     任务模型与执行记录
    scheduler  三种调度算法
    engine     逐时间单位的模拟引擎
    loader     任务数据的读写与校验
    ui         图形界面（Tkinter）
"""
