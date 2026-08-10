package tools.unit;

import santak.lib.DeviceUsb;
import santak.serial.xcp.XCPDeviceData;
import monitor1.WindowsUSB;

public class TestBatteryTest {
    public static void main(String[] args) {
        System.out.println("==============================================================================");
        System.out.println(" ⚡ Winpower G2 Native Battery Test Trigger for PPC 2000D");
        System.out.println("==============================================================================");

        try {
            System.load("C:\\Program Files\\WinpowerG2\\jusb.dll");
            System.load("C:\\Program Files\\WinpowerG2\\libUSB_Win.dll");
            System.out.println("✅ Loaded jusb.dll & libUSB_Win.dll successfully!");

            // 1. เรียก DeviceUsb เพื่อให้ Native C-Driver เปิดหาอุปกรณ์
            DeviceUsb devUsb = new DeviceUsb();
            XCPDeviceData[] devices = new XCPDeviceData[32];
            for (int i = 0; i < 32; i++) devices[i] = new XCPDeviceData();

            int count = devUsb.findAllUsb(devices, 32);
            System.out.println("✅ พบอุปกรณ์ผ่าน DeviceUsb: " + count + " เครื่อง");

            for (int i = 0; i < count; i++) {
                int vid = devices[i].getVendorId();
                String sn = devices[i].getSerialNumber();
                System.out.println("\n  [" + i + "] VID=0x" + Integer.toHexString(vid).toUpperCase() + " | SN=" + sn);

                boolean opened = devUsb.openOneDevice(i);
                System.out.println("    --> openOneDevice(" + i + "): " + opened);

                if (opened) {
                    System.out.println("    ⚡ กำลังส่งคำสั่ง Battery Test 'T\\r' ผ่าน setReport...");

                    // Payload คำสั่ง Q1 "T\r"
                    byte[] q1Test = new byte[] { (byte)'T', (byte)'\r', 0, 0, 0, 0, 0, 0 };

                    // setReport(TYPE_FEATURE=2, ReportID=0x24, q1Test, 8)
                    int r1 = devUsb.setReport(2, 0x24, q1Test, 8);
                    System.out.println("    --> setReport(Feature 0x24): " + r1);

                    // setReport(TYPE_FEATURE=2, ReportID=0x01, q1Test, 8)
                    int r2 = devUsb.setReport(2, 0x01, q1Test, 8);
                    System.out.println("    --> setReport(Feature 0x01): " + r2);

                    devUsb.closeDevice();
                } else {
                    System.out.println("    ⚠️ openOneDevice คืนค่า false (เกิดข้อผิดพลาด hid_force_openEx error=13)");
                    System.out.println("    👉 ต้องรัน Command Prompt ด้วยสิทธิ์ Administrator เท่านั้น!");
                }
            }

        } catch (Throwable t) {
            System.err.println("❌ Exception: " + t.getMessage());
            t.printStackTrace();
        }

        System.out.println("\n==============================================================================");
        System.out.println(" Execution completed.");
        System.out.println("==============================================================================");
    }
}
