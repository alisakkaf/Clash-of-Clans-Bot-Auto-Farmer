# LEGAL DISCLAIMER & TERMS OF USE

Please read this document carefully before using, copying, modifying, or distributing any part of the **ClashOfClans-CV-Automation** framework. By interacting with this software, you agree to be bound by the terms outlined below.

---

## 1. Educational and Research Purposes Only
This framework is an open-source research project demonstrating the integration of **PyQt5 GUI styling**, **OpenCV Multi-Scale Template Matching**, **EasyOCR models**, and **Android Debug Bridge (ADB) automation**. 
- It is designed solely as a developer sandbox, accessibility-emulation demonstration, and educational proof-of-concept.
- It is **not** intended for unfair gameplay advantages or commercial exploitation.

## 2. Non-Intrusive Design (No Cheating/Hacking)
Unlike traditional hacks or cheats, this framework does **not**:
- Read, modify, or inject code into the memory space of any game application process.
- Hook system calls or bypass security components (like client integrity checks or anti-cheat systems).
- Modify or patch official game binaries (`.apk` or `.so` files).
- Intercept, decrypt, modify, or replay network packets.

Instead, this framework operates entirely at the **operating system level** as an external tool, analogous to accessibility assistants, screen readers, or robotic hardware interfaces:
1. It requests the screen display using standard OS-level screenshot APIs (ADB `screencap`).
2. It processes the visual image inside standard user-space RAM using standard computer vision libraries (OpenCV, Pillow).
3. It emulates standard touchscreen inputs via standard OS input drivers (ADB `input tap`, `input swipe`, `getevent`).

## 3. Compliance with Game Terms of Service
Supercell's Terms of Service and Safe Play Policy generally prohibit the use of third-party tools, bots, and automated programs that interact with the game. 
- Executing this framework on an emulator or device connected to live game servers may violate the publisher's Terms of Service.
- Using this tool on live servers carries a significant risk of account suspension or permanent bans.
- The developers of this project **strongly discourage** using this framework on any live, valuable, or competitive accounts.

## 4. Limitation of Liability & No Warranty
This software is provided "AS IS", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and non-infringement.
- In no event shall the authors, developers, or copyright holders be liable for any claim, damages, account suspensions, device malfunctions, data loss, or other liabilities, whether in an action of contract, tort, or otherwise, arising from, out of, or in connection with the software or the use or other dealings in the software.
- You are solely responsible for compliance with any local laws, agreements, and policies. If your use of this framework results in account penalties or losses, you bear the sole responsibility and cost.
