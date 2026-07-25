# คู่มือการใช้งาน `ups_module` สำหรับ Linux 🐧

โมดูล `ups_module` ทำงานบน Linux ได้อย่างราบรื่นโดยใช้ไดรเวอร์ `hidraw` และ `usbhid` ที่มาพร้อมกับ Kernel ของ Linux แทบทุกตัวอยู่แล้ว

## 🌟 ฟีเจอร์เด่นบน Linux
- **ทำงานได้ทันที (Out of the box):** ไม่ต้องติดตั้งโปรแกรม WinpowerG2 หรือไดรเวอร์ภายนอกใดๆ
- **ไม่ต้องยุ่งยากกับ Filter Driver:** ระบบ Linux ยอมให้อ่านค่า Report พิเศษต่างๆ (เช่น Input Voltage) ทะลุผ่าน `hidraw` หรือ `libusb` ได้โดยตรง
- **รองรับ Raspberry Pi & Servers:** เหมาะอย่างยิ่งสำหรับนำไปทำระบบมอนิเตอร์บนเครื่องเซิร์ฟเวอร์ หรือบอร์ด IoT

---

## 🚀 การเริ่มต้นใช้งาน

คุณสามารถรันโค้ด `ups_module` ได้ทันที แต่สิ่งสำคัญที่สุดบน Linux คือ **"สิทธิ์ในการเข้าถึงอุปกรณ์ USB" (Permissions)**

ตามค่าเริ่มต้นของ Linux อุปกรณ์ USB มักจะสงวนสิทธิ์ไว้ให้สิทธิ์ระดับ Root (`sudo`) เท่านั้น 
หากคุณรันสคริปต์ด้วย User ธรรมดา อาจจะเจอ Error แจ้งว่า `Access Denied` หรือหามอดูลไม่เจอ

### วิธีที่ 1: รันด้วยสิทธิ์ Root (รวดเร็วที่สุดสำหรับการทดสอบ)
```bash
sudo python3 demo_ups_module.py
```

### วิธีที่ 2: ตั้งค่า udev Rules (แนะนำสำหรับการใช้งานจริงระยะยาว)
เพื่อให้ User ธรรมดาสามารถอ่านค่า UPS ได้โดยไม่ต้องพิมพ์ `sudo` ทุกครั้ง:
1. สร้างไฟล์ rule ใหม่ใน `/etc/udev/rules.d/`
   ```bash
   sudo nano /etc/udev/rules.d/99-ups.rules
   ```
2. ใส่โค้ดนี้ลงไป (แทนที่ VID:PID ด้วย 06da:ffff ของ UPS คุณ)
   ```text
   SUBSYSTEM=="usb", ATTRS{idVendor}=="06da", ATTRS{idProduct}=="ffff", MODE="0666"
   SUBSYSTEM=="hidraw", ATTRS{idVendor}=="06da", ATTRS{idProduct}=="ffff", MODE="0666"
   ```
3. รีโหลด udev rules และดึงสาย USB ออกแล้วเสียบใหม่
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```
หลังจากนั้นคุณสามารถรันสคริปต์ด้วย User ธรรมดาได้เลย!

---

## 💻 ตัวอย่างโค้ดเบื้องต้น

```python
from ups_module import UPSClient

# ใช้กับ Linux ได้สบายๆ โค้ดเหมือนฝั่ง Windows เป๊ะ!
with UPSClient() as client:
    print("สถานะ UPS:", client.get_status())
    print("แบตเตอรี่คงเหลือ:", client.get_var("battery.charge"), "%")
    print("แรงดันไฟเข้า:", client.get_var("input.voltage"), "V")
```

---

## ⚠️ ระบบการดึงโวลต์ล่องหน (Fallback Mechanism)
แม้ว่า Linux จะค่อนข้างเปิดกว้างกว่า Windows แต่ในบาง Kernel หาก `hidapi` ดึงค่า Voltage ไม่สำเร็จ `ups_module` จะสลับไปใช้ไลบรารี `pyusb` อัตโนมัติ โดยกระบวนการจะเป็นดังนี้:
1. ปลด Kernel Driver ชั่วคราว (`detach_kernel_driver`)
2. ส่งคำสั่ง Raw USB Control Transfer เพื่อดึงโวลต์ 214V มาให้
3. นำ Kernel Driver กลับมาผูกใหม่ (`attach_kernel_driver`)
กระบวนการนี้ทำงานอัตโนมัติในเสี้ยววินาที ผู้ใช้ไม่ต้องตั้งค่าอะไรเพิ่มเติมครับ
