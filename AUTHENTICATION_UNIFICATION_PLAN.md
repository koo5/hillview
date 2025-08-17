# Authentication Unification Plan

## Overview
This plan unifies authentication for both web app and Android mobile app builds, ensuring token synchronization between the frontend and background services while maintaining existing web functionality.

## Current State Analysis

### ✅ Already Implemented
- Complete JWT authentication system with 30-minute expiry
- OAuth2 integration for Google and GitHub
- User registration/login endpoints (`/api/auth/*`)
- Token blacklisting and refresh logic
- Role-based access control
- Frontend login page at `/login`
- OAuth redirect handling

### 🎯 Goals
1. Maintain existing web app authentication flow
2. Enable unified authentication for Android app via system browser
3. Synchronize tokens between frontend and background services
4. Support autonomous background service operation

## Implementation Strategy

### Phase 1: Backend OAuth Callback Enhancement

#### 1.1 Smart OAuth Callback Detection
**File**: `backend/api/app/user_routes.py`

Modify existing `/api/auth/oauth` endpoint to detect request source and handle different response formats:

```python
@router.get("/auth/oauth-callback")
async def oauth_callback(
    code: str,
    state: Optional[str] = None, 
    redirect_uri: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Enhanced OAuth callback that supports both web and mobile flows
    """
    # Exchange code for JWT using existing logic
    jwt_token, expires_at = await exchange_oauth_code_for_jwt(code, db)
    
    # Detect if this is a mobile app request
    if redirect_uri and redirect_uri.startswith("com.hillview://"):
        # Mobile app: deep link back with token
        return RedirectResponse(f"{redirect_uri}?token={jwt_token}&expires_at={expires_at.isoformat()}")
    else:
        # Web app: existing behavior (cookie + redirect to dashboard)
        response = RedirectResponse("/dashboard")
        response.set_cookie(
            "auth_token", 
            jwt_token, 
            httponly=True,
            secure=True,
            samesite="lax",
            expires=expires_at
        )
        return response
```

#### 1.2 OAuth Redirect Endpoint
**File**: `backend/api/app/user_routes.py`

Add new endpoint to initiate OAuth flow with proper redirect URI:

```python
@router.get("/auth/oauth-redirect")
async def oauth_redirect(
    provider: str,
    redirect_uri: str,
    request: Request
):
    """
    Initiate OAuth flow with proper redirect URI for both web and mobile
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")
    
    provider_config = OAUTH_PROVIDERS[provider]
    
    # Build OAuth URL with proper redirect URI
    auth_url = URL(provider_config["auth_url"])
    auth_url = auth_url.replace(query={
        "client_id": provider_config["client_id"],
        "redirect_uri": provider_config["redirect_uri"],  # Your server callback
        "response_type": "code",
        "scope": "email profile" if provider == "google" else "user:email",
        "state": redirect_uri  # Store final destination in state
    })
    
    return RedirectResponse(str(auth_url))
```

### Phase 2: Tauri Plugin Token Management

#### 2.1 Add Authentication Commands
**File**: `frontend/tauri-plugin-hillview/src/commands.rs`

```rust
use android_logger::Config;
use jni::objects::{JObject, JString};
use jni::sys::jstring;
use jni::JNIEnv;
use tauri::{command, AppHandle, Runtime};

#[command]
pub async fn store_auth_token<R: Runtime>(
    app: AppHandle<R>,
    token: String,
    expires_at: String,
) -> Result<(), String> {
    app.plugin_invoke("store_auth_token", serde_json::json!({
        "token": token,
        "expires_at": expires_at
    }))
    .map_err(|e| format!("Failed to store auth token: {}", e))
}

#[command]
pub async fn get_auth_token<R: Runtime>(
    app: AppHandle<R>,
) -> Result<Option<String>, String> {
    app.plugin_invoke("get_auth_token", serde_json::json!({}))
        .map_err(|e| format!("Failed to get auth token: {}", e))
}

#[command]
pub async fn refresh_auth_token<R: Runtime>(
    app: AppHandle<R>,
) -> Result<Option<String>, String> {
    app.plugin_invoke("refresh_auth_token", serde_json::json!({}))
        .map_err(|e| format!("Failed to refresh auth token: {}", e))
}

#[command]
pub async fn clear_auth_token<R: Runtime>(
    app: AppHandle<R>,
) -> Result<(), String> {
    app.plugin_invoke("clear_auth_token", serde_json::json!({}))
        .map_err(|e| format!("Failed to clear auth token: {}", e))
}
```

#### 2.2 Android Authentication Manager
**File**: `frontend/tauri-plugin-hillview/android/src/main/java/AuthenticationManager.kt`

```kotlin
package ch.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import org.json.JSONObject
import java.io.IOException
import java.time.Instant
import java.time.format.DateTimeFormatter

class AuthenticationManager(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val httpClient = OkHttpClient()

    companion object {
        private const val TAG = "AuthenticationManager"
        private const val PREFS_NAME = "hillview_auth"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val KEY_EXPIRES_AT = "expires_at"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val SERVER_URL = "https://your-server.com" // TODO: Make configurable
    }

    fun storeAuthToken(token: String, expiresAt: String) {
        Log.d(TAG, "Storing auth token, expires at: $expiresAt")
        prefs.edit()
            .putString(KEY_AUTH_TOKEN, token)
            .putString(KEY_EXPIRES_AT, expiresAt)
            .apply()
    }

    fun getValidToken(): String? {
        val token = prefs.getString(KEY_AUTH_TOKEN, null) ?: return null
        val expiresAt = prefs.getString(KEY_EXPIRES_AT, null) ?: return null

        // Check if token is expired
        try {
            val expiry = Instant.from(DateTimeFormatter.ISO_INSTANT.parse(expiresAt))
            val now = Instant.now()
            
            if (now.isAfter(expiry.minusSeconds(60))) { // Refresh 1 minute before expiry
                Log.d(TAG, "Token is expired or expiring soon, attempting refresh")
                return refreshToken()
            }
            
            Log.d(TAG, "Token is valid, expires at: $expiresAt")
            return token
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing token expiry: ${e.message}")
            return null
        }
    }

    private fun refreshToken(): String? {
        // For now, return null - background service will need to handle auth failure
        // In future, implement refresh token logic here
        Log.w(TAG, "Token refresh not implemented yet")
        clearAuthToken()
        return null
    }

    fun clearAuthToken() {
        Log.d(TAG, "Clearing auth token")
        prefs.edit()
            .remove(KEY_AUTH_TOKEN)
            .remove(KEY_EXPIRES_AT)
            .remove(KEY_REFRESH_TOKEN)
            .apply()
    }

    fun hasValidToken(): Boolean {
        return getValidToken() != null
    }
}
```

#### 2.3 Update Plugin Commands
**File**: `frontend/tauri-plugin-hillview/android/src/main/java/HillviewPlugin.kt`

Add authentication commands to existing plugin:

```kotlin
// Add to existing HillviewPlugin class
private lateinit var authManager: AuthenticationManager

override fun load(webView: WebView) {
    super.load(webView)
    authManager = AuthenticationManager(activity)
}

@Command
fun storeAuthToken(invoke: Invoke) {
    val args = invoke.parseArgs(StoreAuthTokenArgs::class.java)
    authManager.storeAuthToken(args.token, args.expiresAt)
    invoke.resolve()
}

@Command
fun getAuthToken(invoke: Invoke) {
    val token = authManager.getValidToken()
    val ret = JSObject()
    if (token != null) {
        ret.put("token", token)
    }
    invoke.resolve(ret)
}

@Command
fun clearAuthToken(invoke: Invoke) {
    authManager.clearAuthToken()
    invoke.resolve()
}

// Add argument classes
@InvokeArg
class StoreAuthTokenArgs {
    var token: String? = null
    var expiresAt: String? = null
}
```

### Phase 3: Frontend Integration

#### 3.1 Update Login Page Mobile Detection
**File**: `frontend/src/routes/login/+page.svelte`

Add mobile app detection and appropriate OAuth URL generation:

```typescript
// Add to existing login page script
import { invoke } from '@tauri-apps/api/tauri';

let isMobileApp = false;

onMount(async () => {
    // Detect if we're in a Tauri mobile app
    try {
        await invoke('get_auth_token');
        isMobileApp = true;
    } catch {
        isMobileApp = false;
    }
});

function buildOAuthUrl(provider: string): string {
    const redirectUri = isMobileApp 
        ? "com.hillview://auth"  // Deep link for mobile
        : `${window.location.origin}/oauth-callback`;  // Web callback
        
    return `/api/auth/oauth-redirect?provider=${provider}&redirect_uri=${encodeURIComponent(redirectUri)}`;
}

// Update OAuth button handlers
function handleGoogleLogin() {
    window.location.href = buildOAuthUrl('google');
}

function handleGithubLogin() {
    window.location.href = buildOAuthUrl('github');
}
```

#### 3.2 Handle Deep Link Authentication
**File**: `frontend/src/lib/auth.ts`

Create authentication utility to handle deep link callbacks:

```typescript
import { invoke } from '@tauri-apps/api/tauri';
import { goto } from '$app/navigation';
import { browser } from '$app/environment';

export interface AuthToken {
    token: string;
    expires_at: string;
}

export async function handleAuthCallback(url: string): Promise<boolean> {
    if (!browser) return false;
    
    try {
        const urlObj = new URL(url);
        const token = urlObj.searchParams.get('token');
        const expiresAt = urlObj.searchParams.get('expires_at');
        
        if (token && expiresAt) {
            // Store token in Android SharedPreferences
            await invoke('store_auth_token', { token, expiresAt });
            
            // Redirect to dashboard
            await goto('/dashboard');
            return true;
        }
    } catch (error) {
        console.error('Error handling auth callback:', error);
    }
    
    return false;
}

export async function getStoredToken(): Promise<string | null> {
    try {
        const result = await invoke('get_auth_token') as { token?: string };
        return result.token || null;
    } catch {
        return null;
    }
}

export async function clearStoredToken(): Promise<void> {
    try {
        await invoke('clear_auth_token');
    } catch (error) {
        console.error('Error clearing token:', error);
    }
}
```

#### 3.3 Update Background Service Authentication
**File**: `frontend/tauri-plugin-hillview/android/src/main/java/PhotoUploadWorker.kt`

Integrate AuthenticationManager into existing upload worker:

```kotlin
// Update existing PhotoUploadWorker class
class PhotoUploadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    
    private val authManager = AuthenticationManager(applicationContext)
    
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        Log.d(TAG, "PhotoUploadWorker started")
        
        // Check authentication before proceeding
        val authToken = authManager.getValidToken()
        if (authToken == null) {
            Log.w(TAG, "No valid auth token available, skipping upload work")
            return@withContext Result.success()
        }
        
        try {
            scanForNewPhotos()
            
            val autoUploadEnabled = getAutoUploadSetting()
            if (autoUploadEnabled) {
                processUploadQueue(authToken)
                retryFailedUploads(authToken)
            }
            
            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "PhotoUploadWorker failed", e)
            Result.retry()
        }
    }
    
    private suspend fun processUploadQueue(authToken: String) {
        // Update existing method to use authToken
        // Pass authToken to UploadManager methods
    }
}
```

### Phase 4: Configuration and Integration

#### 4.1 Add Plugin Commands to Frontend
**File**: `frontend/src-tauri/src/lib.rs`

Register new authentication commands:

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_hillview::init())
        .plugin(tauri_plugin_web_auth::init()) // Add web auth plugin
        .invoke_handler(tauri::generate_handler![
            // Add new auth commands
            tauri_plugin_hillview::commands::store_auth_token,
            tauri_plugin_hillview::commands::get_auth_token,
            tauri_plugin_hillview::commands::clear_auth_token,
            // ... existing commands
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

#### 4.2 Add Deep Link Intent Filter
**File**: `frontend/src-tauri/gen/android/app/src/main/AndroidManifest.xml`

```xml
<!-- Add to existing MainActivity intent filters -->
<intent-filter>
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="com.hillview" android:host="auth" />
</intent-filter>
```

## Testing Strategy

### Phase 1 Testing: Backend
1. Test existing web OAuth flow still works
2. Test new OAuth redirect endpoint
3. Test callback detection for mobile vs web
4. Verify JWT generation and response formats

### Phase 2 Testing: Mobile Plugin
1. Test token storage and retrieval via Tauri commands
2. Test AuthenticationManager token validation
3. Test SharedPreferences persistence across app restarts
4. Test background service access to stored tokens

### Phase 3 Testing: Integration
1. Test complete mobile OAuth flow: app → browser → deep link → token storage
2. Test background service authentication with stored tokens
3. Test token expiry handling and fallback behavior
4. Test both web and mobile flows work simultaneously

## Security Considerations

1. **Token Storage**: Use Android SharedPreferences with appropriate security flags
2. **Deep Link Validation**: Validate deep link URLs and token parameters
3. **Token Expiry**: Always check token expiry before use
4. **Fallback Handling**: Graceful degradation when authentication fails
5. **HTTPS Only**: Ensure all OAuth flows use HTTPS in production

## Future Enhancements

1. **Refresh Tokens**: Implement refresh token support for longer background operation
2. **Biometric Auth**: Add biometric authentication for token access
3. **Token Encryption**: Encrypt stored tokens in SharedPreferences
4. **Multi-Device Sync**: Sync authentication state across user devices

## Implementation Order

1. ✅ **Phase 1**: Backend OAuth callback enhancement
2. ✅ **Phase 2**: Tauri plugin authentication commands
3. ✅ **Phase 3**: Frontend mobile detection and integration
4. ✅ **Phase 4**: Configuration and testing
5. 🔄 **Testing**: Comprehensive testing of all flows
6. 🚀 **Deployment**: Production deployment with monitoring

## Success Criteria

- [x] Existing web app authentication continues to work unchanged
- [ ] Mobile app can authenticate via system browser and deep links
- [ ] Tokens are properly synchronized between frontend and background services
- [ ] Background service can operate autonomously with stored tokens
- [ ] Token expiry is handled gracefully in all scenarios
- [ ] Both username/password and OAuth flows work in mobile app