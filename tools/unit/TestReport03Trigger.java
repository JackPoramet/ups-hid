package tools.unit;

import santak.lib.DeviceUsb;
import santak.serial.xcp.XCPDeviceData;

public class TestReport03Trigger {
    public static void main(String[] args) {
        System.out.println("==============================================================================");
        System.out.println(" ⚡ WinPower G2 ReportID 0x03 Hardware Battery Test Trigger");
        System.out.println("==============================================================================");

        try {
            System.load("C:\\Program Files\\WinpowerG2\\jusb.dll");
            System.load("C:\\Program Files\\WinpowerG2\\libUSB_Win.dll");

            DeviceUsb devUsb = new DeviceUsb();
            XCPDeviceData[] devices = new XCPDeviceData[32];
            for (int i = 0; i < 32; i++) devices[i] = new XCPDeviceData();

            int count = devUsb.findAllUsb(devices, 32);
            System.out.println("✅ พบอุปกรณ์ผ่าน WinPower Native Driver: " + count + " เครื่อง");

            if (count > 0 && devUsb.openOneDevice(0)) {
                System.out.println("✅ เปิดพอร์ต USB Device Handle สำเร็จ!");

                byte[] q1Test = new byte[] { (byte)'T', (byte)'\r', 0, 0, 0, 0, 0, 0 };

                System.out.println("\n⚡ [TRIGGER 1] สั่ง setReport(TYPE_FEATURE=2, ReportID=0x03, payload='T\\r')...");
                int res1 = devUsb.setReport(2, 0x03, q1Test, 8);
                System.out.println("    --> ผลลัพธ์ (ret code): " + res1 + (res1 == 8 ? " [ส่งสำเร็จ 8 บิต!]" : " [ล้มเหลว]"));

                System.out.println("⚡ [TRIGGER 2] สั่ง setReport(TYPE_REPORT=1, ReportID=0x07, payload='T\\r')...");
                int res2 = devUsb.setReport(1, 0x07, q1Test, 8);
                System.out.println("    --> ผลลัพธ์ (ret code): " + res2 + (res2 == 8 ? " [ส่งสำเร็จ 8 บิต!]" : " [ล้มเหลว]"));

                System.out.println("⚡ [TRIGGER 3] สั่ง setReport(TYPE_REPORT=1, ReportID=0x25, payload='T\\r')...");
                int res3 = devUsb.setReport(1, 0x25, q1Test, 8);
                System.out.println("    --> ผลลัพธ์ (ret code): " + res3 + (res3 == 8 ? " [ส่งสำเร็จ 8 บิต!]" : " [ล้มเหลว]"));

                System.out.println("\n==============================================================================");
                System.out.println(" 🎉 คำสั่งถูกส่งเข้าวงจรฮาร์ดแวร์ PPC 2000D เรียบร้อยแล้ว!");
                System.out.println(" 🔊 โปรดสังเกตเสียง RELAY CLICK สลับสวิตช์และเสียง BEEP จาก UPS!");
                System.out.println("==============================================================================");

                devUsb.closeDevice();
            } else {
                System.out.println("❌ ไม่สามารถเปิดอุปกรณ์ได้ (ต้องรันในสิทธิ์ Administrator)");
            }
        } catch (Throwable t) {
            t.printStackTrace();
        }
    }
}
