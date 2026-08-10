package tools.unit;

import monitor1.WindowsUSB;
import santak.lib.DeviceUsb;
import santak.serial.xcp.XCPDeviceData;
import java.util.List;

public class TestOrderUPSDirect {
    public static void main(String[] args) {
        System.out.println("==============================================================================");
        System.out.println(" 🚀 WinPower G2 Native Engine Self-Test Trigger (PPC 2000D)");
        System.out.println("==============================================================================");

        try {
            System.load("C:\\Program Files\\WinpowerG2\\jusb.dll");
            System.load("C:\\Program Files\\WinpowerG2\\libUSB_Win.dll");
            System.out.println("✅ Loaded jusb.dll & libUSB_Win.dll successfully!");

            System.out.println("⏳ Waiting 3 seconds for Windows PnP device re-enumeration...");
            Thread.sleep(3000);

            // ------------------------------------------------------------------
            // 1. ใช้ DeviceUsb เปิดการเชื่อมต่อเพื่อขอ Handle Native
            // ------------------------------------------------------------------
            DeviceUsb devUsb = new DeviceUsb();
            XCPDeviceData[] devices = new XCPDeviceData[32];
            for (int i = 0; i < 32; i++) devices[i] = new XCPDeviceData();

            int count = devUsb.findAllUsb(devices, 32);
            System.out.println("✅ พบอุปกรณ์ผ่าน DeviceUsb.findAllUsb: " + count + " เครื่อง");

            if (count > 0) {
                for (int i = 0; i < count; i++) {
                    int vid = devices[i].getVendorId();
                    String sn = devices[i].getSerialNumber();
                    System.out.println("\n  [" + i + "] VID=0x" + Integer.toHexString(vid).toUpperCase() + " | SN=" + sn);

                    boolean opened = devUsb.openOneDevice(i);
                    System.out.println("    --> openOneDevice(" + i + "): " + opened);

                    if (opened) {
                        System.out.println("    ⚡ กำลังส่งคำสั่ง Q1 'T\\r' ผ่าน setReport(2, 0x03)...");
                        byte[] q1Test = new byte[] { (byte)'T', (byte)'\r', 0, 0, 0, 0, 0, 0 };
                        
                        // setReport(TYPE_FEATURE=2, ReportID=0x03, payload, 8)
                        int r1 = devUsb.setReport(2, 0x03, q1Test, 8);
                        System.out.println("    --> setReport(Feature 0x03): " + r1);

                        // setReport(TYPE_REPORT=1, ReportID=0x07, payload, 8)
                        int r2 = devUsb.setReport(1, 0x07, q1Test, 8);
                        System.out.println("    --> setReport(Interrupt 0x07): " + r2);

                        devUsb.closeDevice();
                    }
                }
            }

            // ------------------------------------------------------------------
            // 2. ใช้ WindowsUSB.getInstance() เพื่อส่ง OrderUPS("T", 4, handle)
            // ------------------------------------------------------------------
            System.out.println("\n--- [METHOD 2: WindowsUSB.OrderUPS('T', 4, handle)] ---");
            WindowsUSB winUsb = WindowsUSB.getInstance();
            List<Long> handles = winUsb.searchAllUsbDevices();
            System.out.println("✅ Total handles found via searchAllUsbDevices: " + (handles != null ? handles.size() : 0));

            if (handles != null && !handles.isEmpty()) {
                for (int i = 0; i < handles.size(); i++) {
                    long h = handles.get(i);
                    int vid = winUsb.getVendorIdByDev(h);
                    int pid = winUsb.getProductIdByDev(h);

                    System.out.println("  [" + i + "] VID=0x" + Integer.toHexString(vid).toUpperCase() 
                                       + " PID=0x" + Integer.toHexString(pid).toUpperCase() 
                                       + " Handle=0x" + Long.toHexString(h));

                    if (vid == 0x06DA && pid == 0xFFFF) {
                        System.out.println("  🎯 Sending WindowsUSB.OrderUPS('T', 4, 1000, handle)...");
                        String reply = winUsb.OrderUPS("T", 4, 1000, h);
                        System.out.println("  --> Reply: '" + reply + "'");
                    }
                }
            }

            System.out.println("\n==============================================================================");
            System.out.println(" 🔊 LISTEN FOR RELAY CLICK & BEEP SOUND FROM UPS HARDWARE!");
            System.out.println("==============================================================================");

        } catch (Throwable t) {
            System.err.println("❌ Exception: " + t.getMessage());
            t.printStackTrace();
        }
    }
}
