import usb.core
import usb.core
import usb.util
import time
import libusb_package # เพิ่มบรรทัดนี้

VID = 0x06DA
PID = 0xFFFF

def pyusb_megatec_hack():
    # ค้นหาอุปกรณ์ โดยระบุ backend ให้ชัดเจน
    dev = usb.core.find(idVendor=VID, idProduct=PID, backend=libusb_package.get_libusb1_backend())

    if dev is None:
        raise ValueError('❌ ไม่พบ UPS! (ตรวจสอบสาย USB หรือลองดูใน Zadig)')
    print("✅ พบ UPS แล้ว กำลังเชื่อมต่อผ่าน libusb/WinUSB...")

    # 2. ตั้งค่า Configuration เริ่มต้น
    try:
        dev.set_configuration()
    except usb.core.USBError as e:
        print(f"⚠️ คำเตือนตอน Set Config (อาจจะข้ามได้): {e}")

    # 3. เตรียมคำสั่ง Q1\r (บวก Padding ให้ครบ 8 Bytes)
    command_str = "Q1\r"
    cmd_bytes = [ord(c) for c in command_str]
    while len(cmd_bytes) < 8:
        cmd_bytes.append(0x00)

    print(f"👉 กำลังส่งคำสั่ง: {command_str.strip()} (Hex: {[hex(x) for x in cmd_bytes]})")

    try:
        # =======================================================
        # 🚀 ยิงคำสั่ง SET_REPORT (ยัดข้อมูลเข้าทาง Control Transfer)
        # bmRequestType: 0x21 = Host to Device | Class | Interface
        # bRequest: 0x09 = SET_REPORT
        # wValue: 0x0300 = Feature Report (0x03) + Report ID 0 (0x00)
        # =======================================================
        dev.ctrl_transfer(
            bmRequestType=0x21, 
            bRequest=0x09, 
            wValue=0x0300, # ถ้าดึงไม่เข้า ลองเปลี่ยน Report ID ตรงนี้ เช่น 0x03FE (ID 254)
            wIndex=0, 
            data_or_wLength=cmd_bytes
        )
        
        time.sleep(0.3) # รอ UPS คำนวณ

        # =======================================================
        # 📥 ดึงข้อมูล GET_REPORT (อ่านข้อมูลกลับทาง Control Transfer)
        # bmRequestType: 0xA1 = Device to Host | Class | Interface
        # bRequest: 0x01 = GET_REPORT
        # =======================================================
        response = dev.ctrl_transfer(
            bmRequestType=0xA1, 
            bRequest=0x01, 
            wValue=0x0300, # ต้องตรงกับ wValue ตอนส่ง
            wIndex=0, 
            data_or_wLength=256 # ขออ่าน 256 bytes
        )

        if response:
            # แปลง Bytes กลับเป็น String
            reply = "".join([chr(c) for c in response if 32 <= c <= 126])
            print(f"\n🎉 สำเร็จ! UPS ตอบกลับมาว่า: {reply}")
        else:
            print("\n❌ ไม่มีข้อความตอบกลับ")

    except usb.core.USBError as e:
        print(f"\n❌ Error จาก USB: {e}")

if __name__ == "__main__":
    pyusb_megatec_hack()