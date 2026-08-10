package tools.unit;

import santak.lib.DeviceUsb;
import santak.serial.xcp.XCPDeviceData;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

public class TestJusb {

    // Path ของ log file ที่ Elevated process จะเขียนผล
    private static final String LOG_FILE = "D:\\Work\\CoE\\Project\\UPS\\tools\\unit\\admin_result.log";

    private static boolean isAdmin() {
        try {
            ProcessBuilder pb = new ProcessBuilder("net", "session");
            pb.redirectErrorStream(true);
            Process p = pb.start();
            p.waitFor();
            return p.exitValue() == 0;
        } catch (Exception e) {
            return false;
        }
    }

    private static void elevateAndRun() throws Exception {
        String javaExe = ProcessHandle.current().info().command()
            .orElse(System.getProperty("java.home") + File.separator + "bin" + File.separator + "java.exe");
        String classPath = System.getProperty("java.class.path").replace("\"", "\\\"");
        String libPath   = System.getProperty("java.library.path").replace("\"", "\\\"");

        // เขียน log เริ่มต้น - Java ที่ elevated จะเขียนทับเองผ่าน --elevated flag
        writeLog("[ELEVATE] Requesting Admin elevation via UAC...\n");

        // NOTE: PowerShell Start-Process ไม่รองรับ -RedirectStandardOutput พร้อมกับ -Verb RunAs
        // แก้ไขโดยส่ง --elevated flag เพื่อให้ Java เขียน log file เอง
        String javaArgs = String.format(
            "-Djava.library.path=\"%s\" -cp \"%s\" tools.unit.TestJusb --elevated",
            libPath, classPath
        );
        String psCmd = String.format(
            "Start-Process -FilePath '%s' -ArgumentList '%s' -Verb RunAs -Wait",
            javaExe.replace("'", "''"),
            javaArgs.replace("'", "''")
        );

        System.out.println("[INFO] Requesting UAC elevation... (Click 'Yes' in the UAC dialog)");
        ProcessBuilder pb = new ProcessBuilder("powershell", "-NoProfile", "-Command", psCmd);
        pb.inheritIO();
        Process p = pb.start();
        int exit = p.waitFor();
        System.out.println("[INFO] Elevated process exited with code: " + exit);

        // อ่าน log file แล้วแสดงผล
        System.out.println();
        System.out.println("=== [Elevated Process Output] ===");
        File logFile = new File(LOG_FILE);
        if (logFile.exists()) {
            String content = new String(java.nio.file.Files.readAllBytes(logFile.toPath()));
            System.out.println(content);
        } else {
            System.out.println("[WARN] Log file not created. UAC may have been denied.");
        }
        File errFile = new File(LOG_FILE + ".err");
        if (errFile.exists() && errFile.length() > 0) {
            String errContent = new String(java.nio.file.Files.readAllBytes(errFile.toPath()));
            System.out.println("[STDERR]\n" + errContent);
        }
    }

    private static void writeLog(String text) {
        try (PrintWriter pw = new PrintWriter(new FileWriter(LOG_FILE, false))) {
            pw.print(text);
        } catch (Exception ignored) {}
    }

    public static void main(String[] args) {
        boolean isElevated = false;
        for (String a : args) {
            if ("--elevated".equals(a)) { isElevated = true; break; }
        }

        // Redirect stdout to log file when running as elevated subprocess
        if (isElevated) {
            try {
                PrintWriter pw = new PrintWriter(new FileWriter(LOG_FILE, false), true);
                System.setOut(new java.io.PrintStream(new java.io.OutputStream() {
                    public void write(int b) {
                        pw.write(b);
                        pw.flush();
                    }
                }));
            } catch (Exception ignored) {}
        }

        System.out.println("==============================================================================");
        System.out.println(" Winpower G2 Native Hardware Battery Test Trigger for PPC 2000D");
        System.out.println("==============================================================================");

        if (!isAdmin()) {
            System.out.println("[WARN] Not running as Administrator.");
            try {
                elevateAndRun();
            } catch (Exception e) {
                System.err.println("[ERROR] Could not self-elevate: " + e.getMessage());
                System.err.println("[MANUAL] Right-click run_2000d_test_admin.bat -> 'Run as administrator'");
            }
            return;
        }

        System.out.println("[OK] Running with Administrator rights!");
        System.out.println();

        try {
            System.load("C:\\Program Files\\WinpowerG2\\jusb.dll");
            System.load("C:\\Program Files\\WinpowerG2\\libUSB_Win.dll");

            DeviceUsb devUsb = new DeviceUsb();
            XCPDeviceData[] devices = new XCPDeviceData[32];
            for (int i = 0; i < 32; i++) {
                devices[i] = new XCPDeviceData();
            }

            int count = devUsb.findAllUsb(devices, 32);
            System.out.println("[INFO] Found " + count + " device(s) via Winpower Native Driver");

            for (int i = 0; i < count; i++) {
                int vid = devices[i].getVendorId();
                String sn = devices[i].getSerialNumber();
                System.out.println();
                System.out.println("  [" + i + "] VID=0x" + Integer.toHexString(vid) + " | Serial=" + sn);

                boolean opened = devUsb.openOneDevice(i);
                System.out.println("    --> openOneDevice(): " + opened);

                if (opened) {
                    // Q1 "T\r" = Quick Battery Test, 10-second self-test
                    byte[] q1Test = new byte[8];
                    q1Test[0] = (byte) 'T';
                    q1Test[1] = (byte) '\r';

                    // TYPE_FEATURE=2 (native libusb feature report)
                    int r1 = devUsb.setReport(2, 0x24, q1Test, 8);
                    System.out.println("    --> setReport(TYPE_FEATURE=2, id=0x24, 'T\\r'): " + r1
                        + (r1 >= 0 ? "  *** SUCCESS - relay click + beep expected! ***" : "  [failed]"));

                    if (r1 < 0) {
                        int r2 = devUsb.setReport(2, 0x01, q1Test, 8);
                        System.out.println("    --> setReport(TYPE_FEATURE=2, id=0x01, 'T\\r'): " + r2
                            + (r2 >= 0 ? "  *** SUCCESS ***" : "  [failed]"));
                    }

                    // TYPE_REPORT=1 (interrupt endpoint)
                    int r3 = devUsb.setReport(1, 0x00, q1Test, 8);
                    System.out.println("    --> setReport(TYPE_REPORT=1,   id=0x00, 'T\\r'): " + r3
                        + (r3 >= 0 ? "  *** SUCCESS ***" : "  [failed]"));

                    devUsb.closeDevice();
                } else {
                    System.out.println("    [FAIL] Cannot open device (hid_force_openEx failed even with Admin?)");
                }
            }

        } catch (Throwable t) {
            System.err.println("[ERROR] " + t.getMessage());
            t.printStackTrace();
        }

        System.out.println();
        System.out.println("==============================================================================");
        System.out.println(" Done.");
        System.out.println("==============================================================================");
    }
}
