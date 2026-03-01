// WebGLBridge Fix for Android Build
// This file shows how to fix the undefined symbol errors

// Option 1: Use conditional compilation to exclude WebGL code on Android
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
