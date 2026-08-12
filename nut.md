1. ไฟล์โปรแกรมและตัวสั่งการ (Executables / Binaries)
นี่คือตำแหน่งที่เก็บตัวรันโปรแกรมหลักๆ ของ NUT:

/lib/nut/ : เป็นโฟลเดอร์ที่เก็บ Driver ของ UPS ทั้งหมด (เช่น blazer_usb, usbhid-ups, snmp-ups)

/sbin/ หรือ /usr/sbin/ : เก็บโปรแกรมฝั่งเซิร์ฟเวอร์และมอนิเตอร์ เช่น upsd (ตัวเซิร์ฟเวอร์), upsmon (ตัวมอนิเตอร์), และ upsdrvctl (ตัวควบคุม Driver)

/bin/ หรือ /usr/bin/ : เก็บคำสั่งฝั่งไคลเอนต์ (Client) สำหรับให้ผู้ใช้พิมพ์เรียกดูสถานะ เช่น upsc (ดูข้อมูล UPS), upsrw, upscmd

2. ไฟล์ตั้งค่า (Configuration Files)
/etc/nut/ : ตำแหน่งนี้คุณคุ้นเคยดีอยู่แล้ว มันคือโฟลเดอร์ที่เก็บไฟล์คอนฟิกทั้งหมด เช่น ups.conf, upsd.conf, upsmon.conf เป็นต้น (ซึ่งตัวโปรแกรมจะวิ่งมาอ่านการตั้งค่าจากที่นี่)

3. ไฟล์จัดการ Service (Systemd)
/lib/systemd/system/ : เป็นที่เก็บไฟล์ .service ที่เอาไว้ให้ระบบปฏิบัติการสั่ง Start/Stop/Restart โปรแกรมเบื้องหลัง เช่น nut-driver.service, nut-server.service, และ nut-monitor.service

4. ไฟล์สถานะการทำงาน (Runtime Data & PID)
เมื่อโปรแกรมกำลังทำงาน มันจะสร้างไฟล์ชั่วคราวเพื่อคุยกันเองภายในระบบ:

/run/nut/ (หรือ /var/run/nut/) : เก็บไฟล์ PID (Process ID) และ Socket เพื่อให้โปรแกรมรู้ว่าตัวเองรันอยู่

/var/state/ups/ : โฟลเดอร์ชั่วคราวที่ Driver ใช้เขียนสถานะของ UPS เพื่อให้ upsd (Server) มาอ่านไปแสดงผลต่อ

ทำการทดสอบบน Pi เพื่อสร้างไดร์ฟเวอร์สำหรับใช้กับ Nut

สิ่งที่ได้ติดตั้งลงไปแล้ว
apt update
apt install nut nut-server nut-client -y

sudo apt install nut-cgi -y

## nut tool
# 1. ติดตั้งเครื่องมือคอมไพล์บน Pi (ถ้ายังไม่มี)
sudo apt update
sudo apt install autoconf automake libtool pkg-config build-essential libusb-1.0-0-dev -y

# 2. คอมไพล์โค้ด
dos2unix autogen.sh tools/*.sh  # กันเหนียวเรื่อง \r
chmod +x autogen.sh
./autogen.sh
./configure --with-usb
make
make distclean **สำหรับคลีน

mkdir -p /var/state/ups
chown nut:nut /var/state/ups

upsc myups
upsc myups ups.status

# รีโหลดสิทธิ์และเปิดใช้งาน Service
sudo systemctl daemon-reload
sudo systemctl restart nut-server
sudo systemctl restart nut-client