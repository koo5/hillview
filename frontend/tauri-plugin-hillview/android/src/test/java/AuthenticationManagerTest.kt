package io.github.koo5.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import org.junit.Before
import org.junit.Test
import org.junit.Assert.*
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.Mockito.*
import java.time.Instant
import java.time.format.DateTimeFormatter

class AuthenticationManagerTest {

    @Mock
    private lateinit var mockContext: Context

    @Mock
    private lateinit var mockSharedPreferences: SharedPreferences

    @Mock
    private lateinit var mockEditor: SharedPreferences.Editor

    private lateinit var authManager: AuthenticationManager

    @Before
    fun setUp() {
        MockitoAnnotations.openMocks(this)
        
        // Set up mocks
        `when`(mockContext.getSharedPreferences("hillview_auth", Context.MODE_PRIVATE))
            .thenReturn(mockSharedPreferences)
        `when`(mockSharedPreferences.edit()).thenReturn(mockEditor)
        `when`(mockEditor.putString(any(), any())).thenReturn(mockEditor)
        `when`(mockEditor.remove(any())).thenReturn(mockEditor)
        
        authManager = AuthenticationManager(mockContext)
    }

    @Test
    fun testStoreAuthToken_Success() {
        // Arrange
        val token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        val expiresAt = "2023-12-01T10:30:00Z"

        // Act
        val result = authManager.storeAuthToken(token, expiresAt)

        // Assert
        assertTrue(result)
        verify(mockEditor).putString("auth_token", token)
        verify(mockEditor).putString("expires_at", expiresAt)
        verify(mockEditor).apply()
    }

    @Test
    fun testStoreAuthToken_Exception() {
        // Arrange
        val token = "test_token"
        val expiresAt = "2023-12-01T10:30:00Z"
        
        doThrow(RuntimeException("Storage error"))
            .`when`(mockEditor).apply()

        // Act
        val result = authManager.storeAuthToken(token, expiresAt)

        // Assert
        assertFalse(result)
    }

    @Test
    fun testGetValidToken_ValidToken() {
        // Arrange
        val token = "valid_jwt_token"
        val futureTime = Instant.now().plusSeconds(3600) // 1 hour from now
        val expiresAt = DateTimeFormatter.ISO_INSTANT.format(futureTime)
        
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(token)
        `when`(mockSharedPreferences.getString("expires_at", null)).thenReturn(expiresAt)

        // Act
        val result = authManager.getValidToken()

        // Assert
        assertEquals(token, result)
    }

    @Test
    fun testGetValidToken_ExpiredToken() {
        // Arrange
        val token = "expired_jwt_token"
        val pastTime = Instant.now().minusSeconds(3600) // 1 hour ago
        val expiresAt = DateTimeFormatter.ISO_INSTANT.format(pastTime)
        
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(token)
        `when`(mockSharedPreferences.getString("expires_at", null)).thenReturn(expiresAt)

        // Act
        val result = authManager.getValidToken()

        // Assert
        assertNull(result)
    }

    @Test
    fun testGetValidToken_ExpiringToken() {
        // Arrange - token expires in 30 seconds (should be considered expired)
        val token = "expiring_jwt_token"
        val soonTime = Instant.now().plusSeconds(30)
        val expiresAt = DateTimeFormatter.ISO_INSTANT.format(soonTime)
        
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(token)
        `when`(mockSharedPreferences.getString("expires_at", null)).thenReturn(expiresAt)

        // Act
        val result = authManager.getValidToken()

        // Assert
        assertNull(result) // Should be null because it expires in less than 1 minute
    }

    @Test
    fun testGetValidToken_NoToken() {
        // Arrange
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(null)

        // Act
        val result = authManager.getValidToken()

        // Assert
        assertNull(result)
    }

    @Test
    fun testGetValidToken_NoExpiryDate() {
        // Arrange
        val token = "token_without_expiry"
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(token)
        `when`(mockSharedPreferences.getString("expires_at", null)).thenReturn(null)

        // Act
        val result = authManager.getValidToken()

        // Assert
        assertNull(result)
    }

    @Test
    fun testGetValidToken_InvalidExpiryFormat() {
        // Arrange
        val token = "token_with_invalid_expiry"
        val invalidExpiresAt = "invalid_date_format"
        
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(token)
        `when`(mockSharedPreferences.getString("expires_at", null)).thenReturn(invalidExpiresAt)

        // Act
        val result = authManager.getValidToken()

        // Assert
        assertNull(result)
    }

    @Test
    fun testGetTokenInfo() {
        // Arrange
        val token = "test_token"
        val expiresAt = "2023-12-01T10:30:00Z"
        
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(token)
        `when`(mockSharedPreferences.getString("expires_at", null)).thenReturn(expiresAt)

        // Act
        val result = authManager.getTokenInfo()

        // Assert
        assertEquals(token, result.first)
        assertEquals(expiresAt, result.second)
    }

    @Test
    fun testClearAuthToken_Success() {
        // Act
        val result = authManager.clearAuthToken()

        // Assert
        assertTrue(result)
        verify(mockEditor).remove("auth_token")
        verify(mockEditor).remove("expires_at")
        verify(mockEditor).apply()
    }

    @Test
    fun testClearAuthToken_Exception() {
        // Arrange
        doThrow(RuntimeException("Clear error"))
            .`when`(mockEditor).apply()

        // Act
        val result = authManager.clearAuthToken()

        // Assert
        assertFalse(result)
    }

    @Test
    fun testHasValidToken_True() {
        // Arrange
        val token = "valid_token"
        val futureTime = Instant.now().plusSeconds(3600)
        val expiresAt = DateTimeFormatter.ISO_INSTANT.format(futureTime)
        
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(token)
        `when`(mockSharedPreferences.getString("expires_at", null)).thenReturn(expiresAt)

        // Act
        val result = authManager.hasValidToken()

        // Assert
        assertTrue(result)
    }

    @Test
    fun testHasValidToken_False() {
        // Arrange - no token
        `when`(mockSharedPreferences.getString("auth_token", null)).thenReturn(null)

        // Act
        val result = authManager.hasValidToken()

        // Assert
        assertFalse(result)
    }

    private fun any(): String {
        return org.mockito.ArgumentMatchers.any()
    }
}