import hid
import time

VID = 0x06DA
PID = 0xFFFF

def get_vin_direct():
    try:
        print("🔍 กำลังเชื่อมต่อ UPS...")
        dev = hid.device()
        dev.open(VID, PID)
        dev.set_nonblocking(1)

        # ส่งคำสั่ง Q1 ผ่านประตูลับ (Report ID 9 ที่เราเคยสแกนเจอ)
        print("⚡ กำลังส่งคำสั่ง Q1 ขอข้อมูล Vin...")
        cmd = [0x09, ord('Q'), ord('1'), ord('\r'), 0x00, 0x00, 0x00, 0x00]
        dev.send_feature_report(cmd)
        time.sleep(0.3)

        # ดักฟังคำตอบ 2 ช่องทาง (Interrupt และ Feature)
        reply = dev.read(64, timeout_ms=1000)
        if not reply:
            reply = dev.get_feature_report(0x09, 64)

        if reply:
            # แปลงรหัส Bytes กลับเป็นข้อความ
            text = "".join([chr(c) for c in reply if 32 <= c <= 126])
            print(f"\n🎉 สำเร็จ! ข้อมูลดิบจาก UPS: {text}")
            
            # ถ้า text หน้าตาแบบนี้ "(218.0 230.2 230.2 000 50.0..."
            # เราสามารถตัดเอาเฉพาะ Vin มาโชว์ได้เลย
            if text.startswith("("):
                parts = text.split(" ")
                vin = parts[0].replace("(", "")
                print(f"⚡ แรงดันไฟขาเข้า (Vin) คือ: {vin} V")
        else:
            print("\n❌ ไม่มีข้อความตอบกลับจาก UPS")

        dev.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_vin_direct()