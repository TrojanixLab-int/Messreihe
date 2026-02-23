Messreihe - Utility Tool for Geiger Counters

This program helps to differentiate and identify types of radiation using a Geiger counter.

    No installation required: Simply unpack and start.

    Privacy: The program does not transmit or collect any data.

    Cookie-free: If you want cookies, you'll have to go to the bakery...

Installation & Location

Unpack the "Messreihe" folder from the ZIP file to a location of your choice (e.g., C:\Messreihe or Documents).

    Important: Avoid the system folders "Program Files", "Program Files (x86)", and "Windows", as Windows often blocks or sabotages write operations (log files) in those locations.

How the Measurement Works

The program listens to the default input source (Microphone or Line-In).

    Right-click on the speaker symbol -> Open Volume Mixer.

    Check under "System" > "Input" to ensure the correct device is active.

    Manual Mode: If no microphone is available or the Geiger counter does not have an acoustic "clicker", the values can also be entered manually.

Extras

The linked Nukliddaten.exe can be called up directly via the "Nuclide Data" button.
Further details can be found in the attached Messreihe.pdf.

--- Troubleshooting ---

If the program does not start or if Windows causes trouble, please note the following points:

Symptom: An error message like "VCRUNTIME140.dll was not found" appears at startup.
Solution: Install the "Microsoft Visual C++ Redistributable" package (usually the x64 version for Windows 11).

Problem: Since Messreihe.exe is new and "unknown" to Microsoft, Windows 11 will block the start.
Message: "Windows protected your PC".
Solution: The user must click on "More info" and then on "Run anyway".

Problem: If the program tries to write measurement data into files (e.g., in C:), permissions are often missing on a fresh system.
Message: "You don't have permission to save in this location. Contact the administrator to obtain permission. Would you like to save in the Documents folder instead?"
Solution: The program should ideally be run in a user folder (e.g., Desktop or Documents) or started with Right-click -> Run as administrator.

Problem: After installation, Windows often only provides "Standard Display Drivers". The program renders graphics (with matplotlib) and could crash or lag extremely.
Solution: The user must install the original graphics drivers (NVIDIA, AMD, or Intel).

Message: A black console window flashes briefly and closes immediately with the error message: ModuleNotFoundError: No module named 'matplotlib'
Problem: If the user is named "User", everything is fine. If they are named "Jörg Müller", the program ends up in the path C:\Users\Jörg Müller\.... Some Python libraries cannot handle umlauts in the path.
Solution: Place the program in a path without special characters (e.g., C:\Messreihe\).

Problem: The sensitive Defender can categorically classify "Messreihe.exe" as a "Trojan" (due to a missing certificate) because it behaves like an archive (it unpacks itself into the Temp folder at startup).
Solution: The user must add an exception in Windows Defender for the folder or the file.

Problem: On modern laptops, Windows 11 is often set to 150% or 200% scaling. The program window might look blurry or buttons might be cut off.
Solution: Right-click on Messreihe.exe -> Properties -> Compatibility -> Change high DPI settings.

Problem: If the user creates a shortcut on the desktop but the "Start in" field in the properties is incorrect, the program will no longer find its own configuration files.
Troubleshooting: The program must always remain in the same folder as its associated files.