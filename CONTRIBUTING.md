# Contributing to ClashOfClans-CV-Automation

Thank you for your interest in improving the **ClashOfClans-CV-Automation** framework! Contributions are welcome, whether they are bug fixes, feature enhancements, documentation updates, or template assets additions.

Please read through the guidelines below before submitting a pull request.

---

## 1. Code of Conduct
We encourage a collaborative, respectful, and educational environment. Be supportive of other developers, keep discussions focused on the technical aspects of computer vision and automation, and respect legal safety parameters (do not submit memory-tampering hacks, network packet spoofing tools, or game file cracks).

## 2. Setting Up the Development Environment
1. Fork the repository and clone your fork locally:
   ```bash
   git clone https://github.com/YourUsername/ClashOfClans-CV-Automation.git
   cd ClashOfClans-CV-Automation
   ```
2. Set up a Python virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up an emulator with a **1920x1080 resolution** and enable ADB connection.

## 3. Contribution Workflow
1. **Create a branch** for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Implement changes:**
   - Keep your code clean, documented, and conform to PEP 8 standards.
   - Maintain the singleton pattern for `Settings` and class architectures.
   - Ensure the anti-ban humanization constraints (coordinate jittering and reaction delays) are respected in any new input actions.
3. **Local Testing:**
   - Run the bot on different emulator configurations to verify compatibility.
   - Ensure no regressions were introduced to the legacy V36 fallback routines.
4. **Commit your changes:**
   - Write clear, descriptive commit messages:
     ```bash
     git commit -m "vision: add scale auto-calibration to isometric grid"
     ```
5. **Push and Open a Pull Request:**
   - Push your branch to your GitHub fork and open a Pull Request against our `main` branch.
   - Describe the purpose of the change, your verification plan, and add screenshots of UI adjustments if applicable.

## 4. Coding Standards
- **Python Formatting:** Follow standard Python styling rules (PEP 8). Keep line lengths under 120 characters where possible.
- **Robust Imports:** Always support relative module imports through the root-level path adjustments implemented in `main.py`.
- **Exception Logging:** Use `BotLogger` instead of `print()` statements so details are preserved in `assets/logs/bot.log`. Wrap vision operations in try-except blocks to prevent crashes on partial or corrupted framebuffers.
