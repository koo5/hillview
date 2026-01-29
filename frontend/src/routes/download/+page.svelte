<script lang="ts">
    import { Download, Smartphone, Send, CheckCircle, AlertCircle } from 'lucide-svelte';
    import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
    import StandardBody from '$lib/components/StandardBody.svelte';
    import { http } from '$lib/http';
	import MyExternalLink from "$lib/components/MyExternalLink.svelte";

    let email = '';
    let submitting = false;
    let submitted = false;
    let error = '';

    async function handleSubmit() {
        if (!email.trim()) {
            error = 'Please enter your email address';
            return;
        }

        submitting = true;
        error = '';

        try {
            const response = await http.post('/contact', {
                contact: email.trim(),
                message: '[Tester Signup] Request to join Android closed testing program'
            });

            if (response.ok) {
                submitted = true;
                email = '';
            } else {
                const errorData = await response.json().catch(() => ({ detail: 'Failed to register' }));
                error = errorData.detail || 'Failed to register';
            }
        } catch (e) {
            error = 'Network error. Please try again later.';
        } finally {
            submitting = false;
        }
    }
</script>

<StandardHeaderWithAlert
    title="Download Hillview"
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>

    <div class="content">
        <div class="hero">
            <div class="icon-container">
                <Smartphone size={64} />
            </div>
<!--            <p class="subtitle">Explore and map your photos on Android</p>-->
        </div>

        <div class="download-section">
<!--            <Download size={24} />-->
<!--            <p>Download Android APK from Google Play - <b>Coming Soon!</b></p>-->

            <div class="tester-signup">
                <h2>Join Closed Testing</h2>
                <p class="tester-description">
                    We're currently in closed testing. Enter your Google account email to get early access.
                </p>

                {#if submitted}
                    <div class="success-message">
                        <CheckCircle size={20} />
                        <span>Thanks! We'll add you to the testing program soon.</span>
                    </div>
                {:else}
                    <form on:submit|preventDefault={handleSubmit} class="tester-form">
                        <div class="input-group">
                            <input
                                type="email"
                                bind:value={email}
                                placeholder="your.email@gmail.com"
                                disabled={submitting}
                                data-testid="tester-email-input"
                            />
                            <button type="submit" disabled={submitting || !email.trim()} data-testid="tester-submit-btn">
                                {#if submitting}
                                    Sending...
                                {:else}
                                    <Send size={16} />
                                    Sign Up
                                {/if}
                            </button>
                        </div>
                        {#if error}
                            <div class="error-message">
                                <AlertCircle size={16} />
                                {error}
                            </div>
                        {/if}
                    </form>
                {/if}
            </div>

        </div>

		<br/><br/><br/><br/><br/><br/>
			<MyExternalLink href="https://play.google.com/store/apps/details?id=cz.hillview" >Hillview on Google Play Store (Closed testing)</MyExternalLink>

    </div>
</StandardBody>

<style>




    .content {
        max-width: 800px;
        margin: 0 auto;
        padding: 2.5rem;
        text-align: center;
    }

    .hero {
        margin-bottom: 0rem;
    }

    .icon-container {
        margin-bottom: 0.5rem;
        opacity: 0.9;
    }

    .download-section {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }

    .tester-signup {
        margin-top: 2rem;
        padding-top: 2rem;
        border-top: 1px solid rgba(255, 255, 255, 0.2);
    }

    .tester-signup h2 {
        font-size: 1.5rem;
        margin: 0 0 0.5rem 0;
        font-weight: 500;
    }

    .tester-description {
        opacity: 0.8;
        margin-bottom: 1.5rem;
    }

    .tester-form {
        max-width: 400px;
        margin: 0 auto;
    }

    .input-group {
        display: flex;
        gap: 0.5rem;
    }

    .input-group input {
        flex: 1;
        padding: 12px 16px;
        border: 1px solid rgba(5, 225, 5, 0.3);
        border-radius: 8px;
        font-size: 1rem;
        background: rgba(255, 255, 255, 0.9);
    }

    .input-group input:focus {
        outline: none;
        border-color: #4f46e5;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.2);
    }

    .input-group input:disabled {
        opacity: 0.7;
        cursor: not-allowed;
    }

    .input-group button {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 12px 20px;
        background: #4f46e5;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        white-space: nowrap;
    }

    .input-group button:hover:not(:disabled) {
        background: #3730a3;
    }

    .input-group button:disabled {
        background: #9ca3af;
        cursor: not-allowed;
    }

    .success-message {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        background: rgba(16, 185, 129, 0.2);
        border: 1px solid rgba(16, 185, 129, 0.4);
        color: #10b981;
        padding: 16px;
        border-radius: 8px;
    }

    .error-message {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.3);
        color: #ef4444;
        padding: 12px;
        border-radius: 8px;
        margin-top: 1rem;
        font-size: 0.875rem;
    }

    @media (max-width: 768px) {
        .content {
            padding: 1rem;
        }

        .download-section {
            padding: 1.5rem;
        }

        .input-group {
            flex-direction: column;
        }

        .input-group button {
            justify-content: center;
        }
    }
</style>
