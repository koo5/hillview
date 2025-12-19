<svelte:head>
	<title>Account Deletion - Hillview</title>
</svelte:head>

<script lang="ts">
    import { User, Trash2, LogIn, Mail, ArrowRight, Shield } from 'lucide-svelte';
    import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
    import StandardBody from '$lib/components/StandardBody.svelte';
    import { auth } from '$lib/auth.svelte';
</script>

<StandardHeaderWithAlert
    title="Account Deletion"
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>
    <div class="deletion-container">
        <header class="deletion-header">
            <div class="deletion-icon">
                <Trash2 size={32} />
            </div>
            <h1>Delete Your Account</h1>
            <p class="deletion-tagline">
                We understand you may want to delete your account. Here's how you can do it.
            </p>
        </header>

        <div class="instructions-container">
            {#if $auth.user}
                <!-- User is logged in - show account deletion instructions -->
                <div class="instruction-card logged-in">
                    <div class="card-header">
                        <User size={24} />
                        <h2>You're currently logged in as <strong>{$auth.user.username}</strong></h2>
                    </div>

                    <div class="steps-container">
                        <p>You can delete your account directly from your account settings page.</p>

                        <div class="quick-action">
                            <a href="/account" class="btn-primary" data-testid="go-to-account-btn">
                                <User size={16} />
                                Go to Account Settings
                                <ArrowRight size={16} />
                            </a>
                        </div>

                        <div class="simple-instructions">
                            <p>On the account page, scroll down to find the "Delete Account" button and follow the confirmation process.</p>
                        </div>

                        <div class="warning-notice">
                            <Shield size={20} />
                            <div>
                                <strong>Important:</strong> Account deletion is permanent and cannot be undone.
                                All your photos, data, and account information will be permanently removed.
                            </div>
                        </div>
                    </div>
                </div>
            {:else}
                <!-- User is not logged in - show login instructions -->
                <div class="instruction-card not-logged-in">
                    <div class="card-header">
                        <LogIn size={24} />
                        <h2>You need to log in first</h2>
                    </div>

                    <div class="login-instructions">
                        <p>To delete your account, you must first log in to verify your identity.</p>

                        <div class="login-steps">
                            <h3>Option 1: Log in and delete your account</h3>
                            <p>Log in to access your account settings where you can delete your account.</p>

                            <div class="action-button">
                                <a href="/login" class="btn-primary" data-testid="login-btn">
                                    <LogIn size={16} />
                                    Log In to Your Account
                                </a>
                            </div>
                        </div>

                        <div class="divider">
                            <span>OR</span>
                        </div>

                        <div class="contact-option">
                            <h3>Option 2: Contact us for assistance</h3>
                            <p>
                                If you're unable to log in to your account, or need assistance with account deletion,
                                please contact us and we'll help you with the process.
                            </p>

                            <div class="action-button">
                                <a href="/contact" class="btn-secondary" data-testid="contact-btn">
                                    <Mail size={16} />
                                    Contact Support
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            {/if}

            <!-- Additional information section -->
            <div class="additional-info">
                <h3>What happens when you delete your account?</h3>
                <ul class="deletion-effects">
                    <li>All your uploaded photos will be permanently removed</li>
                    <li>Your account information and profile data will be deleted</li>
                </ul>
				This action cannot be reversed

                <div class="contact-fallback">
                    <h4>Need help or have questions?</h4>
                    <p>
                        If you encounter any issues during the account deletion process,
                        or if you have questions about what data will be deleted, please
                        <a href="/contact" data-testid="contact-fallback-link">contact our support team</a>.
                    </p>
                </div>
            </div>
        </div>
    </div>
</StandardBody>

<style>
    .deletion-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 0 16px;
    }

    .deletion-header {
        text-align: center;
        margin-bottom: 48px;
    }

    .deletion-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 64px;
        height: 64px;
        background: linear-gradient(135deg, #fef2f2, #fecaca);
        border-radius: 16px;
        color: #dc2626;
        margin-bottom: 16px;
    }

    .deletion-header h1 {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f2937;
        margin: 0 0 16px 0;
    }

    .deletion-tagline {
        font-size: 1.125rem;
        color: #4b5563;
        margin: 0;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
    }

    .instructions-container {
        display: flex;
        flex-direction: column;
        gap: 32px;
    }

    .instruction-card {
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .card-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 1px solid #e5e7eb;
    }

    .logged-in .card-header {
        color: #059669;
    }

    .not-logged-in .card-header {
        color: #dc2626;
    }

    .card-header h2 {
        margin: 0;
        font-size: 1.25rem;
        font-weight: 600;
    }

    .steps-container h3,
    .login-instructions h3 {
        font-size: 1.125rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 16px 0;
    }

    .simple-instructions {
        margin-top: 16px;
        padding: 16px;
        background: #f9fafb;
        border-radius: 8px;
        border-left: 4px solid #4f46e5;
    }

    .simple-instructions p {
        margin: 0;
        color: #4b5563;
        font-size: 0.875rem;
    }

    .quick-action {
        margin-bottom: 24px;
    }

    .warning-notice {
        display: flex;
        gap: 12px;
        background: #fef3cd;
        border: 1px solid #f59e0b;
        color: #92400e;
        padding: 16px;
        border-radius: 8px;
        font-size: 0.875rem;
    }

    .login-instructions {
        display: flex;
        flex-direction: column;
        gap: 24px;
    }

    .login-steps ol {
        margin: 0 0 16px 0;
        padding-left: 20px;
    }

    .login-steps li {
        margin-bottom: 8px;
        color: #4b5563;
    }

    .action-button {
        display: flex;
        justify-content: center;
    }

    .btn-primary {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: #4f46e5;
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 1rem;
        text-decoration: none;
    }

    .btn-primary:hover {
        background: #3730a3;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }

    .btn-secondary {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: white;
        color: #4f46e5;
        border: 1px solid #4f46e5;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 1rem;
        text-decoration: none;
    }

    .btn-secondary:hover {
        background: #f9fafb;
        transform: translateY(-1px);
    }

    .divider {
        text-align: center;
        position: relative;
        margin: 24px 0;
    }

    .divider::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 0;
        right: 0;
        height: 1px;
        background: #e5e7eb;
    }

    .divider span {
        background: rgba(255, 255, 255, 0.8);
        padding: 0 16px;
        color: #6b7280;
        font-weight: 500;
    }

    .contact-option p {
        color: #4b5563;
        margin: 0 0 16px 0;
        line-height: 1.5;
    }

    .additional-info {
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .additional-info h3 {
        font-size: 1.125rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 16px 0;
    }

    .deletion-effects {
        margin: 0 0 24px 0;
        padding-left: 20px;
    }

    .deletion-effects li {
        margin-bottom: 8px;
        color: #4b5563;
    }

    .contact-fallback {
        padding-top: 24px;
        border-top: 1px solid #e5e7eb;
    }

    .contact-fallback h4 {
        font-size: 1rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 8px 0;
    }

    .contact-fallback p {
        color: #4b5563;
        margin: 0;
        line-height: 1.5;
    }

    .contact-fallback a {
        color: #4f46e5;
        text-decoration: none;
        font-weight: 500;
    }

    .contact-fallback a:hover {
        text-decoration: underline;
    }

    /* Responsive design */
    @media (max-width: 768px) {
        .deletion-header h1 {
            font-size: 2rem;
        }

        .instruction-card {
            padding: 24px;
        }

        .card-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 8px;
        }

        .step {
            flex-direction: column;
            gap: 12px;
        }

        .step-number {
            align-self: flex-start;
        }

        .btn-primary,
        .btn-secondary {
            width: 100%;
            justify-content: center;
        }
    }
</style>
