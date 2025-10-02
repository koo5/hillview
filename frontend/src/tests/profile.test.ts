import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { render, fireEvent, waitFor, screen } from '@testing-library/svelte';
import { goto } from '$app/navigation';
import { invoke } from '@tauri-apps/api/core';
import ProfilePage from '../routes/account/+page.svelte';
import { auth } from '$lib/auth.svelte';

// Mock dependencies
vi.mock('$app/navigation');
vi.mock('@tauri-apps/api/core');
vi.mock('$lib/auth.svelte');

const mockGoto = goto as Mock;
const mockInvoke = invoke as Mock;
const mockAuth = auth as any;

// Mock fetch globally
global.fetch = vi.fn();
const mockFetch = fetch as Mock;

describe('Profile Page', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        
        // Default auth state
        mockAuth.subscribe = vi.fn((callback) => {
            callback({ isAuthenticated: true, token: 'test-token' });
            return () => {}; // unsubscribe function
        });
        
        // Default mobile app detection (web app)
        mockInvoke.mockRejectedValue(new Error('Not mobile app'));
    });

    describe('Authentication Flow', () => {
        it('should redirect to login if not authenticated', async () => {
            mockAuth.subscribe = vi.fn((callback) => {
                callback({ isAuthenticated: false, token: null });
                return () => {};
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(mockGoto).toHaveBeenCalledWith('/login');
            });
        });

        it('should stay on page if authenticated', async () => {
            mockAuth.subscribe = vi.fn((callback) => {
                callback({ isAuthenticated: true, token: 'test-token' });
                return () => {};
            });

            render(ProfilePage);

            // Should not redirect to login
            expect(mockGoto).not.toHaveBeenCalledWith('/login');
        });
    });

    describe('Profile Data Loading', () => {
        it('should load user profile data successfully', async () => {
            const mockProfileData = {
                id: '123',
                username: 'testuser',
                email: 'test@example.com',
                is_active: true,
                created_at: '2024-01-01T00:00:00Z',
                provider: null
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockProfileData)
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(screen.getByText('testuser')).toBeInTheDocument();
                expect(screen.getByText('test@example.com')).toBeInTheDocument();
                expect(screen.getByText('Username & Password')).toBeInTheDocument();
            });

            expect(mockFetch).toHaveBeenCalledWith(
                expect.stringContaining('/user/profile'),
                expect.objectContaining({
                    headers: expect.objectContaining({
                        'Authorization': 'Bearer test-token'
                    })
                })
            );
        });

        it('should display OAuth provider badge for OAuth users', async () => {
            const mockOAuthData = {
                id: '123',
                username: 'testuser',
                email: 'test@example.com',
                is_active: true,
                created_at: '2024-01-01T00:00:00Z',
                provider: 'google'
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockOAuthData)
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(screen.getByText('google OAuth')).toBeInTheDocument();
            });
        });

        it('should handle profile loading errors', async () => {
            mockFetch.mockResolvedValueOnce({
                ok: false,
                status: 500
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(screen.getByText(/Failed to load profile/)).toBeInTheDocument();
            });
        });

        it('should redirect to login on 401 error', async () => {
            mockFetch.mockResolvedValueOnce({
                ok: false,
                status: 401
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(mockGoto).toHaveBeenCalledWith('/login');
            });
        });
    });

    describe('Mobile App Detection', () => {
        it('should detect mobile app and use invoke for token', async () => {
            mockInvoke.mockResolvedValueOnce({
                success: true,
                token: 'mobile-token'
            });

            const mockProfileData = {
                id: '123',
                username: 'mobileuser',
                email: 'mobile@example.com',
                is_active: true,
                created_at: '2024-01-01T00:00:00Z',
                provider: null
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockProfileData)
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(mockInvoke).toHaveBeenCalledWith('get_auth_token');
            });

            expect(mockFetch).toHaveBeenCalledWith(
                expect.stringContaining('/user/profile'),
                expect.objectContaining({
                    headers: expect.objectContaining({
                        'Authorization': 'Bearer mobile-token'
                    })
                })
            );
        });

        it('should handle mobile token retrieval failure', async () => {
            mockInvoke.mockResolvedValueOnce({
                success: false,
                token: null
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(screen.getByText(/No authentication token found/)).toBeInTheDocument();
            });
        });
    });

    describe('Logout Functionality', () => {
        it('should handle logout successfully', async () => {
            const mockLogout = vi.fn().mockResolvedValue(undefined);
            vi.doMock('$lib/auth.svelte', () => ({
                auth: mockAuth,
                logout: mockLogout
            }));

            mockFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve({
                    username: 'testuser',
                    email: 'test@example.com'
                })
            });

            render(ProfilePage);

            await waitFor(() => {
                expect(screen.getByText('Sign Out')).toBeInTheDocument();
            });

            const logoutButton = screen.getByText('Sign Out');
            await fireEvent.click(logoutButton);

            await waitFor(() => {
                expect(mockLogout).toHaveBeenCalled();
                expect(mockGoto).toHaveBeenCalledWith('/');
            });
        });

        it('should handle logout errors', async () => {
            const mockLogout = vi.fn().mockRejectedValue(new Error('Logout failed'));
            vi.doMock('$lib/auth.svelte', () => ({
                auth: mockAuth,
                logout: mockLogout
            }));

            mockFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve({
                    username: 'testuser',
                    email: 'test@example.com'
                })
            });

            render(ProfilePage);

            const logoutButton = await screen.findByText('Sign Out');
            await fireEvent.click(logoutButton);

            await waitFor(() => {
                expect(screen.getByText(/Failed to logout properly/)).toBeInTheDocument();
            });
        });
    });

    describe('Account Deletion', () => {
        beforeEach(async () => {
            mockFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve({
                    username: 'testuser',
                    email: 'test@example.com'
                })
            });
        });

        it('should show delete confirmation modal', async () => {
            render(ProfilePage);

            const deleteButton = await screen.findByText('Delete Account');
            await fireEvent.click(deleteButton);

            await waitFor(() => {
                expect(screen.getByText('Type DELETE to confirm:')).toBeInTheDocument();
                expect(screen.getByPlaceholderText('Type DELETE here')).toBeInTheDocument();
            });
        });

        it('should require correct confirmation text', async () => {
            render(ProfilePage);

            const deleteButton = await screen.findByText('Delete Account');
            await fireEvent.click(deleteButton);

            const confirmInput = await screen.findByPlaceholderText('Type DELETE here');
            await fireEvent.input(confirmInput, { target: { value: 'wrong' } });

            const confirmDeleteButton = screen.getByRole('button', { name: /Delete Account/ });
            expect(confirmDeleteButton).toBeDisabled();
        });

        it('should enable delete button with correct confirmation', async () => {
            render(ProfilePage);

            const deleteButton = await screen.findByText('Delete Account');
            await fireEvent.click(deleteButton);

            const confirmInput = await screen.findByPlaceholderText('Type DELETE here');
            await fireEvent.input(confirmInput, { target: { value: 'DELETE' } });

            const confirmDeleteButton = screen.getByRole('button', { name: /Delete Account/ });
            expect(confirmDeleteButton).not.toBeDisabled();
        });

        it('should handle successful account deletion', async () => {
            mockFetch
                .mockResolvedValueOnce({
                    ok: true,
                    json: () => Promise.resolve({ username: 'testuser' })
                })
                .mockResolvedValueOnce({
                    ok: true,
                    json: () => Promise.resolve({ message: 'Account successfully deleted' })
                });

            const mockLogout = vi.fn().mockResolvedValue(undefined);
            vi.doMock('$lib/auth.svelte', () => ({
                auth: mockAuth,
                logout: mockLogout
            }));

            render(ProfilePage);

            // Open delete modal
            const deleteButton = await screen.findByText('Delete Account');
            await fireEvent.click(deleteButton);

            // Enter confirmation
            const confirmInput = await screen.findByPlaceholderText('Type DELETE here');
            await fireEvent.input(confirmInput, { target: { value: 'DELETE' } });

            // Confirm deletion
            const confirmDeleteButton = screen.getByRole('button', { name: /Delete Account/ });
            await fireEvent.click(confirmDeleteButton);

            await waitFor(() => {
                expect(screen.getByText(/Account deleted successfully/)).toBeInTheDocument();
            });

            // Should logout and redirect after delay
            await new Promise(resolve => setTimeout(resolve, 2100));
            
            expect(mockLogout).toHaveBeenCalled();
            expect(mockGoto).toHaveBeenCalledWith('/');
        });

        it('should handle deletion errors', async () => {
            mockFetch
                .mockResolvedValueOnce({
                    ok: true,
                    json: () => Promise.resolve({ username: 'testuser' })
                })
                .mockResolvedValueOnce({
                    ok: false,
                    json: () => Promise.resolve({ detail: 'Deletion failed' })
                });

            render(ProfilePage);

            // Open delete modal and confirm
            const deleteButton = await screen.findByText('Delete Account');
            await fireEvent.click(deleteButton);

            const confirmInput = await screen.findByPlaceholderText('Type DELETE here');
            await fireEvent.input(confirmInput, { target: { value: 'DELETE' } });

            const confirmDeleteButton = screen.getByRole('button', { name: /Delete Account/ });
            await fireEvent.click(confirmDeleteButton);

            await waitFor(() => {
                expect(screen.getByText(/Deletion failed/)).toBeInTheDocument();
            });
        });

        it('should cancel deletion when clicking cancel', async () => {
            render(ProfilePage);

            const deleteButton = await screen.findByText('Delete Account');
            await fireEvent.click(deleteButton);

            await waitFor(() => {
                expect(screen.getByText('Type DELETE to confirm:')).toBeInTheDocument();
            });

            const cancelButton = screen.getByText('Cancel');
            await fireEvent.click(cancelButton);

            await waitFor(() => {
                expect(screen.queryByText('Type DELETE to confirm:')).not.toBeInTheDocument();
            });
        });
    });

    describe('Date Formatting', () => {
        it('should format dates correctly', async () => {
            const mockProfileData = {
                id: '123',
                username: 'testuser',
                email: 'test@example.com',
                is_active: true,
                created_at: '2024-01-15T14:30:00Z',
                provider: null
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                json: () => Promise.resolve(mockProfileData)
            });

            render(ProfilePage);

            await waitFor(() => {
                // Should format date in readable format
                expect(screen.getByText(/January 15, 2024/)).toBeInTheDocument();
            });
        });
    });
});