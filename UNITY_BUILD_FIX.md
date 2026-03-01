# Unity Android Build Fix - WebGLBridge Undefined Symbols

## Problem
The build is failing because `WebGLBridge` is trying to call JavaScript functions (`SendMessageToReact`, `OnDiceRollComplete`, `OnGameStateChanged`) that only exist in WebGL builds, not Android builds.

## Solution

### Step 1: Find the WebGLBridge Script
Find your `WebGLBridge.cs` file in your Unity project (usually in `Assets/Scripts/` or similar).

### Step 2: Wrap WebGL-specific code with conditional compilation

Replace the WebGLBridge code with this:

```csharp
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;

public class WebGLBridge
{
    [DllImport("__Internal")]
    private static extern void SendMessageToReact(string message);
    
    [DllImport("__Internal")]
    private static extern void OnDiceRollComplete(string results);
    
    [DllImport("__Internal")]
    private static extern void OnGameStateChanged(string state);
    
    public static void SendCustomMessage(string message)
    {
        SendMessageToReact(message);
    }
    
    public static void SendDiceResults(string results)
    {
        OnDiceRollComplete(results);
    }
    
    public static void SendGameState(string state)
    {
        OnGameStateChanged(state);
    }
}
#else
// Android/iOS/Editor builds - provide stub implementations
public class WebGLBridge
{
    public static void SendCustomMessage(string message)
    {
        // Stub implementation for non-WebGL platforms
        UnityEngine.Debug.Log($"[WebGLBridge] SendCustomMessage (stub): {message}");
    }
    
    public static void SendDiceResults(string results)
    {
        // Stub implementation for non-WebGL platforms
        UnityEngine.Debug.Log($"[WebGLBridge] SendDiceResults (stub): {results}");
    }
    
    public static void SendGameState(string state)
    {
        // Stub implementation for non-WebGL platforms
        UnityEngine.Debug.Log($"[WebGLBridge] SendGameState (stub): {state}");
    }
}
#endif
```

### Step 3: Alternative - Disable WebGLBridge for Android

If you don't need WebGLBridge functionality on Android, you can also:

1. **Option A**: Add `#if !UNITY_ANDROID` around the entire WebGLBridge class
2. **Option B**: Create an Android-specific version that doesn't call JavaScript functions

### Step 4: Rebuild

After making the changes:
1. Save the file in Unity
2. Build again: **File → Build Settings → Build**

## Explanation

- `#if UNITY_WEBGL && !UNITY_EDITOR` - Only includes WebGL-specific code when building for WebGL
- `#else` - Provides stub implementations for Android/iOS/Editor builds
- The stubs log to console instead of calling JavaScript functions

This way:
- WebGL builds get the real JavaScript bridge
- Android builds get harmless stubs that just log
- No linker errors!

## Quick Fix Script

If you want to quickly find and fix all WebGLBridge references:

```bash
# Find the file
find . -name "*WebGLBridge*.cs" -o -name "*Bridge*.cs"

# Then edit it to add the conditional compilation
```
