# 🔍 Network Configuration Drift Detector

A Python-based tool that monitors network device configurations and alerts on unauthorized changes by comparing against a known-good Git baseline.

## 🎯 Features

- ✅ Automatic periodic monitoring of network device configs
- 📊 Git-based version control for baseline configurations  
- 🚨 Real-time alerts on configuration drift (LOW/MEDIUM/HIGH severity)
- 📄 Detailed drift reports with diff analysis
- 🔐 SSH-based secure connection to devices
- 📝 Comprehensive logging

## 🛠️ Tech Stack

- Python 3
- Paramiko (SSH)
- GitPython (Git integration)
- PyYAML (Configuration)
- Schedule (Task scheduling)
- Colorama (Terminal colors)

## 📋 Prerequisites

- Linux (tested on Linux Mint)
- Python 3.8+
- FRRouting or any SSH-enabled network device
- Git

## 🚀 Installation

```bash
# Clone this repository
git clone https://github.com/Zubair-Fashoo/network-drift-detector.git
cd network-drift-detector

# Install Python packages
pip3 install paramiko gitpython pyyaml schedule colorama

# Copy config template and edit
cp config.yaml.example config.yaml
nano config.yaml
```

## 📖 Usage

```bash
# 1. Create initial baseline
python3 setup_baseline.py

# 2. Start monitoring
python3 drift_detector.py

# 3. Test with simulated drift
python3 simulate_drift.py
```

## 📁 Project Structure

```
network-drift-detector/
├── drift_detector.py       # Main monitoring script
├── setup_baseline.py       # Baseline creator
├── simulate_drift.py       # Testing tool
├── config.yaml.example     # Config template
├── known_good/             # Baseline configs
├── configs/                # Current configs
└── reports/                # Drift reports
```

## 👨‍💻 Author

**Zubair** - Network Security Project

## 📄 License

MIT License
