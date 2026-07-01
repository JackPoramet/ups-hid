import hid
import time

class PhoenixtecUPS:
    def __init__(self, vendor_id=0x06DA, product_id=0xFFFF):
        self.vid = vendor_id
        self.pid = product_id
        self.device = hid.device()
        
    def connect(self):
        """เปิดการเชื่อมต่อกับ UPS"""
        self.device.open(self.vid, self.pid)
        # ดึงข้อมูลประจำตัวเครื่อง (Identification)
        manufacturer = self.device.get_manufacturer_string()
        product = self.device.get_product_string()
        serial = self.device.get_serial_number_string()
        print(f"🔌 เชื่อมต่อสำเร็จ: {manufacturer} {product} (SN: {serial})")

    def disconnect(self):
        """ปิดการเชื่อมต่อ"""
        self.device.close()

    def safe_get_report(self, report_id, size):
        """ฟังก์ชันดึงข้อมูลแบบป้องกัน Error (หากหน้าไหนเครื่องไม่ส่งมา ให้ข้ามไป)"""
        try:
            return self.device.get_feature_report(report_id, size)
        except ValueError:
            return None

    def get_u16(self, data, start_idx):
        """แปลงข้อมูล 16-bit (2 Bytes) แบบ Little Endian"""
        if data and len(data) >= start_idx + 2:
            return data[start_idx] | (data[start_idx+1] << 8)
        return 0

    def get_u32(self, data, start_idx):
        """แปลงข้อมูล 32-bit (4 Bytes) แบบ Little Endian"""
        if data and len(data) >= start_idx + 4:
            return data[start_idx] | (data[start_idx+1] << 8) | (data[start_idx+2] << 16) | (data[start_idx+3] << 24)
        return 0

    def read_all_data(self):
        """ฟังก์ชันกวาดอ่านค่าทั้งหมดและจัดเก็บในรูปแบบ Dictionary (คล้าย JSON)"""
        metrics = {}
        
        # 🔴 1. กลุ่มสถานะและการแจ้งเตือน (Status Flags)
        r1 = self.safe_get_report(1, 8)
        if r1:
            metrics['ac_present'] = bool(r1[1])
            metrics['below_capacity_limit'] = bool(r1[2]) if len(r1) > 2 else False
            metrics['charging'] = bool(r1[3]) if len(r1) > 3 else False
            metrics['discharging'] = bool(r1[5]) if len(r1) > 5 else False
            metrics['status_good'] = bool(r1[6]) if len(r1) > 6 else False
            
        r2 = self.safe_get_report(2, 8)
        if r2:
            # อ้างอิง Index ตามลำดับ FeatureCaps
            metrics['internal_failure'] = bool(r2[1]) if len(r2) > 1 else False
            metrics['need_replacement'] = bool(r2[2]) if len(r2) > 2 else False
            metrics['overload'] = bool(r2[3]) if len(r2) > 3 else False
            metrics['shutdown_imminent'] = bool(r2[4]) if len(r2) > 4 else False
            
        r3 = self.safe_get_report(3, 8)
        if r3:
            metrics['over_temperature'] = bool(r3[1]) if len(r3) > 1 else False

        # 🔋 2. กลุ่มข้อมูลแบตเตอรี่และรันไทม์ (Battery Metrics)
        r6 = self.safe_get_report(6, 8)
        if r6:
            metrics['battery_capacity_percent'] = r6[1] if len(r6) > 1 else 0
            metrics['runtime_remaining_sec'] = self.get_u32(r6, 2)
            
        r8 = self.safe_get_report(8, 8)
        if r8:
            metrics['low_batt_alert_limit_percent'] = r8[1] if len(r8) > 1 else 0

        # 📊 ข้อมูลผสม: โหลด, อุณหภูมิ, แรงดันแบตเตอรี่ (Power Summary)
        r7 = self.safe_get_report(7, 64)
        if r7:
            metrics['percent_load'] = r7[2] if len(r7) > 2 else 0
            # ดึงอุณหภูมิ (Kelvin -> Celsius)
            temp_k = self.get_u16(r7, 4)
            if temp_k > 0:
                metrics['temperature_c'] = round(temp_k - 273.15, 1)
            # ดึงแรงดันชาร์จแบตเตอรี่ (มักจะซ่อนที่ Index 10-11)
            metrics['battery_voltage_v'] = self.get_u16(r7, 10) / 10.0

        # ⚡ 3. กลุ่มมิเตอร์วัดพลังงานขาออก (Output Power Meter)
        # Report ID 66 (0x42)
        r66 = self.safe_get_report(66, 64) 
        if r66:
            # ใช้ get_u16 ดึงข้อมูลทีละ 2 Bytes ตามลำดับ Descriptor
            metrics['output_active_power_w'] = self.get_u16(r66, 5) 
            metrics['output_apparent_power_va'] = self.get_u16(r66, 7)
            metrics['output_current_a'] = self.get_u16(r66, 9) / 10.0    # กระแสมักมีทศนิยม 1 ตำแหน่ง
            metrics['output_frequency_hz'] = self.get_u16(r66, 11) / 10.0 
            metrics['output_voltage_v'] = self.get_u16(r66, 13) / 10.0   # แรงดัน Vout (เช่น 2300 / 10 = 230.0V)

        # ⚙️ 4. กลุ่มข้อมูลสเปคเครื่อง (System Configuration)
        r20 = self.safe_get_report(20, 8) # Report ID 0x14
        if r20:
            metrics['config_nominal_frequency_hz'] = r20[1] if len(r20) > 1 else 0
            metrics['config_nominal_voltage_v'] = r20[2] if len(r20) > 2 else 0

        r116 = self.safe_get_report(116, 16) # Report ID 0x74
        if r116:
            metrics['config_max_active_power_w'] = self.get_u16(r116, 2)
            metrics['config_max_apparent_power_va'] = self.get_u16(r116, 4)

        # --- สร้างตัวแปร Mode แบบแม่นยำขึ้น ---
        ac_in = metrics.get('ac_present', False)
        batt_discharging = metrics.get('discharging', False)
        vout = metrics.get('output_voltage_v', 0.0)

        if ac_in and not batt_discharging:
            # เช็คว่าเครื่องจ่ายไฟออกไปหาปลั๊กด้านหลังหรือไม่ (ถ้า Vout ต่ำกว่า 50V คือเครื่องปิดอยู่)
            if vout < 50.0: 
                metrics['ups_mode'] = "Standby Mode (เสียบปลั๊ก/ปิดเครื่อง)"
            else:
                metrics['ups_mode'] = "Line Mode (ไฟปกติ)"
                
        elif not ac_in and batt_discharging:
            metrics['ups_mode'] = "Battery Mode (ไฟดับ!)"
            
        elif not ac_in and not batt_discharging:
            # ไม่มีไฟเข้า และไม่ได้ใช้แบต (น่าจะปิดสวิตช์และถอดปลั๊ก)
            metrics['ups_mode'] = "Turned Off"
            
        else:
            metrics['ups_mode'] = "Unknown / Fault"
            
        # เติมสถานะการชาร์จต่อท้าย
        if metrics.get('charging', False):
            metrics['ups_mode'] += " [Charging]"
            
        return metrics

# ==========================================
# ส่วนของการเรียกใช้งาน (Main Execution)
# ==========================================
if __name__ == "__main__":
    ups = PhoenixtecUPS()
    try:
        ups.connect()
        print("-" * 50)
        
        while True:
            # ดึงข้อมูลทั้งหมดในครั้งเดียว
            data = ups.read_all_data()
            
            # จัดฟอร์แมตแสดงผลให้สวยงาม
            print("\033[H\033[J", end="") # เคลียร์หน้าจอ Terminal
            print("=== UPS Monitor ===\n")
            
            for key, value in data.items():
                # เพิ่มหน่วยต่อท้ายให้ดูง่าย
                unit = ""
                if key.endswith('_v'): unit = " V"
                elif key.endswith('_w'): unit = " W"
                elif key.endswith('_va'): unit = " VA"
                elif key.endswith('_a'): unit = " A"
                elif key.endswith('_hz'): unit = " Hz"
                elif key.endswith('_c'): unit = " °C"
                elif key.endswith('_percent'): unit = " %"
                elif key.endswith('_sec'): unit = " s"
                
                print(f"  {key:<35}: {value}{unit}")
                
            time.sleep(2) # อัปเดตข้อมูลทุก 2 วินาที

    except KeyboardInterrupt:
        print("\nหยุดการทำงานโดยผู้ใช้")
    except Exception as e:
        print(f"\nเกิดข้อผิดพลาด: {e}")
    finally:
        ups.disconnect()