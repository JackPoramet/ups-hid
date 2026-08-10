package tools.unit;

import santak.lib.DeviceUsb;
import santak.serial.xcp.XCPDeviceData;

public class TestAllReports {
    public static void main(String[] args) {
        System.out.println("==============================================================================");
        System.out.println(" 🔍 Comprehensive Report ID & Type Scanner for PPC 2000D");
        System.out.println("==============================================================================");

        try {
            System.load("C:\\Program Files\\WinpowerG2\\jusb.dll");
            System.load("C:\\Program Files\\WinpowerG2\\libUSB_Win.dll");

            DeviceUsb devUsb = new DeviceUsb();
            XCPDeviceData[] devices = new XCPDeviceData[32];
            for (int i = 0; i < 32; i++) devices[i] = new XCPDeviceData();

            int count = devUsb.findAllUsb(devices, 32);
            System.out.println("Found " + count + " device(s)");

            if (count > 0 && devUsb.openOneDevice(0)) {
                System.out.println("✅ openOneDevice(0) = true!");

                byte[] q1Bytes = new byte[] { (byte)'T', (byte)'\r', 0, 0, 0, 0, 0, 0 };

                // Test TYPE_REPORT = 1 (Interrupt/Output Report)
                System.out.println("\n--- Testing TYPE_REPORT = 1 (Interrupt OUT) ---");
                for (int rid = 0; rid <= 0x3F; rid++) {
                    int res = devUsb.setReport(1, rid, q1Bytes, 8);
                    if (res >= 0) {
                        System.out.println("  🎯 SUCCESS! TYPE_REPORT=1, ReportID=0x" + Integer.toHexString(rid) + " -> ret=" + res);
                    }
                }

                // Test TYPE_FEATURE = 2 (Feature Report)
                System.out.println("\n--- Testing TYPE_FEATURE = 2 (Feature Report) ---");
                for (int rid = 0; rid <= 0x3F; rid++) {
                    int res = devUsb.setReport(2, rid, q1Bytes, 8);
                    if (res >= 0) {
                        System.out.println("  🎯 SUCCESS! TYPE_FEATURE=2, ReportID=0x" + Integer.toHexString(rid) + " -> ret=" + res);
                    }
                }

                // Test TYPE_STRING = 5 (Set String)
                System.out.println("\n--- Testing TYPE_STRING = 5 (Set Indexed String) ---");
                for (int rid = 0; rid <= 0x10; rid++) {
                    int res = devUsb.setReport(5, rid, q1Bytes, 8);
                    if (res >= 0) {
                        System.out.println("  🎯 SUCCESS! TYPE_STRING=5, Index=0x" + Integer.toHexString(rid) + " -> ret=" + res);
                    }
                }

                devUsb.closeDevice();
            } else {
                System.out.println("❌ Could not open device.");
            }
        } catch (Throwable t) {
            t.printStackTrace();
        }
    }
}
