สร้าง venv
    python -m venv .venv

    source .venv/bin/activate  # สำหรับ Linux/Mac
    .venv\Scripts\activate  # สำหรับ Windows

ติดตั้ง dependencies
    pip install -r requirements.txt

รันโปรแกรม
    python ups_monitor_gui_linux.py  # ใช้ได้ทั้ง Widows และ Linux


UPS ที่ใช้ PHOENIXTEC Innova Unity

สิ่งที่ทำได้
สามารถดูค่าพื้นฐานข้อ UPS ได้ แต่ใน windows Voltage In ยังไม่สามารถดูได้ ซึ่งใน Linux สามารถดูได้ตามปกติ

เมนู Control 
    สามารถสั่ง Self test ตั้งเวลาปิดเครื่อง UPS ได้ สั่งเปิด UPS ได้
    ตั้งปรับแรงดันได้ อยู่ที่ 220V และ 230V ปรับความถี่ได้ที่ 50Hz และ 60Hz
    สามารถปรับนาฬิกาของ UPS ได้

ข้อมูลจากสคริปต์ ได้ทำการนำไปเทียบกับโปรแกรม WinPower G2 แล้วซึ่งตรงกัน