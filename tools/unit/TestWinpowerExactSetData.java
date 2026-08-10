package tools.unit;

import santak.hid.LinuxHidDevice;
import santak.serial.xcp.XCPDeviceData;

public class TestWinpowerExactSetData {
    public static void main(String[] args) {
        System.out.println("==============================================================================");
        System.out.println(" 🎯 Winpower G2 Exact LinuxHidDevice.setIntValue(86, 1) Self-Test Trigger");
        System.out.println("==============================================================================");

        try {
            System.load("C:\\Program Files\\WinpowerG2\\jusb.dll");
            System.load("C:\\Program Files\\WinpowerG2\\libUSB_Win.dll");
            System.out.println("✅ Loaded jusb.dll & libUSB_Win.dll successfully!");

            LinuxHidDevice dev = new LinuxHidDevice();
            XCPDeviceData[] devices = new XCPDeviceData[32];
            for (int i = 0; i < 32; i++) devices[i] = new XCPDeviceData();

            int count = dev.findAllUsb(devices, 32, null);
            System.out.println("✅ Found " + count + " device(s) via LinuxHidDevice");

            for (int i = 0; i < count; i++) {
                int vid = devices[i].getVendorId();
                String sn = devices[i].getSerialNumber();
                System.out.println("\n  [" + i + "] VID=0x" + Integer.toHexString(vid).toUpperCase() + " | SN=" + sn);

                int openRet = dev.openOneDevice(i, vid, sn);
                System.out.println("    --> openOneDevice(" + i + "): ret=" + openRet);

                if (openRet == 0 || openRet == 1) {
                    System.out.println("    ⚡ Executing EXACT Winpower G2 Call: setIntValue(cmd=86, val=1)...");
                    
                    // BATTERY_TESTSWITCHABLE = 86, ACTION_QUICKTEST = 1
                    int res = dev.setIntValue(86, 1);
                    System.out.println("    ➔ setIntValue(cmd=86, val=1) Return Code: " + res);

                    if (res == 0) {
                        System.out.println("\n==============================================================================");
                        System.out.println(" 🎉 SUCCESS! Command setIntValue(86, 1) returned 0!");
                        System.out.println(" 🔊 LISTEN FOR RELAY CLICK & BEEP SOUND FROM PPC 2000D!");
                        System.out.println("==============================================================================");
                    } else {
                        System.out.println("    ⚠️ setIntValue returned code: " + res);
                    }

                    dev.close();
                } else {
                    System.out.println("    ⚠️ openOneDevice failed (ret=" + openRet + "). Run as Administrator!");
                }
            }

        } catch (Throwable t) {
            System.err.println("❌ Exception: " + t.getMessage());
            t.printStackTrace();
        }
    }
}
