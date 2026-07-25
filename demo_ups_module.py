import time
from ups_module import UPSClient, NotifyType

def main():
    print("=== ทดสอบการเรียกใช้งาน ups_module (Plug & Play) ===")
    
    # แบบที่ 1: One-shot Read (อ่านครั้งเดียวแล้วจบ)
    print("\n[1] ทดสอบดึงข้อมูลแบบครั้งเดียว (One-shot Read):")
    with UPSClient() as client:
        status = client.get_status()
        voltage_in = client.get_var("input.voltage")
        charge = client.get_var("battery.charge")
        
        print(f"  -> สถานะ UPS: {status}")
        print(f"  -> แบตเตอรี่: {charge}%")
        print(f"  -> แรงดันไฟเข้า (Input Voltage): {voltage_in} V")
        print("  (ข้อมูล Voltage In นี้ถูกดึงทะลุผ่าน libusb บน Windows / Linux แล้ว!)\n")

    # แบบที่ 2: Event Monitoring (จับตาดูสถานะแบบ Real-time)
    print("[2] ทดสอบระบบ Monitoring (กด Ctrl+C เพื่อหยุด):")
    client = UPSClient()
    client.connect()

    # ตั้งค่า Event Listener เพื่อให้แจ้งเตือนเมื่อเกิดเหตุการณ์ต่างๆ
    @client.on(NotifyType.ONBATT)
    def power_failed(event):
        print("\n⚠️ [แจ้งเตือน] ไฟดับ! UPS สลับไปใช้แบตเตอรี่แล้ว!")

    @client.on(NotifyType.ONLINE)
    def power_restored(event):
        print("\n✅ [แจ้งเตือน] ไฟมาแล้ว! UPS กลับมาใช้ไฟบ้านตามปกติ")

    @client.on(NotifyType.LOWBATT)
    def low_battery(event):
        print("\n🚨 [แจ้งเตือน] แบตเตอรี่ต่ำมาก! เตรียมตัว Shutdown เครื่อง!")

    # สั่งให้ทำงานเบื้องหลัง โดยให้มันดึงข้อมูลใหม่ทุกๆ 1 วินาที
    client.start_monitor(interval=1.0)

    try:
        while True:
            # ดึงชุดข้อมูลทั้งหมดมาดูแบบสดๆ
            data = client.get_vars()
            
            # ดึงค่าเฉพาะที่น่าสนใจมาปริ้นท์
            vin = data.get("input.voltage", "N/A")
            vout = data.get("output.voltage", "N/A")
            load = data.get("ups.load", "N/A")
            batt = data.get("battery.charge", "N/A")
            state = data.get("ups.status", "N/A")
            
            print(f"สดๆ 🟢 สถานะ: {state:<4} | ไฟเข้า: {vin} V | ไฟออก: {vout} V | โหลด: {load}% | แบต: {batt}%", end="\r")
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n\nหยุดการทำงาน...")
    finally:
        client.stop_monitor()
        client.disconnect()
        print("ปิดการเชื่อมต่อ UPS เรียบร้อยแล้ว")

if __name__ == "__main__":
    main()
