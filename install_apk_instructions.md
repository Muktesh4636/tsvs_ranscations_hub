# APK Installation Instructions

## ✅ Step-by-Step Guide

### 1. Install Android Studio (if not already installed)
- Download from: https://developer.android.com/studio
- Install and open Android Studio

### 2. Open the Android Project
```bash
# Open Android Studio
# Click "Open" and navigate to:
/Users/pradyumna/chip_3/chip-3/android_app
```

### 3. Wait for Gradle Sync
- Android Studio will download dependencies (2-3 minutes)

### 4. Build the APK
- Go to **Build** → **Build Bundle(s) / APK(s)** → **Build APK(s)**
- Wait for build to complete (1-2 minutes)
- Click **"locate"** in the notification to find the APK file

### 5. Copy APK to Download Directory
```bash
cp android_app/app/build/outputs/apk/debug/app-debug.apk static/apk/
```

### 6. Download APK to Phone
- Open your browser on phone
- Go to: `http://192.168.1.24:8000/download/apk/`
- Download the APK file

### 7. Install on Phone
- Open the downloaded APK file on your phone
- Tap **"Install"**
- If prompted, allow "Install from Unknown Sources"

## 📱 Alternative: Direct Transfer

### Option A: USB Cable
```bash
# Connect phone via USB, enable USB debugging, then:
adb install android_app/app/build/outputs/apk/debug/app-debug.apk
```

### Option B: File Transfer
- Send APK via WhatsApp/Email/AirDrop to your phone
- Open and install

## 🔧 Server Configuration

✅ **Django server is running** at `http://192.168.1.24:8000/`
✅ **Android app configured** to connect to this server
✅ **Download link ready** at `/download/apk/`

## 🚨 Important Notes

- Make sure your phone and Mac are on the **same WiFi network**
- The server URL in the app is set to your Mac's IP: `192.168.1.24:8000`
- If your IP changes, update `ApiClient.kt` and rebuild the APK

## 📞 Need Help?

If you encounter any issues:
1. Check Android Studio build logs
2. Verify Django server is running (`python3 manage.py runserver 0.0.0.0:8000`)
3. Test connection from phone browser: `http://192.168.1.24:8000/`

The app will login with your Django admin credentials!