<svelte:head>
	<title>Terms of Service - Hillview</title>
</svelte:head>

<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import { FileText, Calendar, Mail, Eye, Shield } from 'lucide-svelte';
</script>

<StandardHeaderWithAlert
	title="Terms of Service"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	<div class="legal-document">
		<header class="document-header">
			<div class="document-icon">
				<FileText size={48} />
			</div>
			<h1>Terms of Service</h1>
			<div class="document-meta">
				<div class="meta-item">
					<Calendar size={16} />
					<span>Last updated: December 2025</span>
				</div>
			</div>
		</header>

		<section class="document-section">
			<h2>1. Acceptance of Terms</h2>
			<p>
				By using Hillview ("the Service"), you agree to be bound by these Terms of Service.
				If you do not agree to these terms, please do not use our service.
			</p>
		</section>

		<section class="document-section">
			<h2>2. Description of Service</h2>
			<p>
				Hillview is a photo mapping application that helps users identify landmarks and features
				from viewpoints using geotagged photos with directional data. The service combines GPS
				coordinates with compass bearing information to create a directional photo database.
			</p>
		</section>

		<section class="document-section">
			<h2>3. User Accounts</h2>
			<p>
				To use certain features of Hillview, you may need to create an account. You are responsible for:
			</p>
			<ul>
				<li>Maintaining the confidentiality of your account credentials</li>
				<li>All activities that occur under your account</li>
				<li>Notifying us immediately of any unauthorized use of your account</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>4. Photo Upload and Content</h2>
			<p>
				When you upload photos to Hillview, you retain ownership of your content but grant us
				certain rights to use it within our service:
			</p>
			<ul>
				<li>You may upload photos that you own or have permission to use</li>
				<li>We process photos to extract metadata (GPS, orientation, etc.)</li>
				<li>Our algorithms detect and blur people and vehicles to try to protect privacy</li>
				<li>You are responsible for ensuring your content doesn't violate any laws or rights</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>
				5. Privacy Protection and Automatic Anonymization
			</h2>

				<p><strong>Important Privacy Features:</strong></p>
				<p>
					Hillview includes automatic privacy protection features designed to protect individuals' privacy:
				</p>
				<ul>
					<li><strong>Automatic Person Blurring:</strong> Our system automatically detects and blurs humans in uploaded photos</li>
					<li><strong>Automatic Vehicle Blurring:</strong> Vehicles are automatically detected and blurred</li>
				</ul>

				<div class="warning-box">
					<Eye size={20} />
					<div>
						<p><strong>User Responsibility for Privacy Compliance:</strong></p>
						<p>
							While our automatic anonymization systems are designed to protect privacy,
							<strong>no automated system is perfect</strong>. Publishing personally identifiable
							information may be illegal in your jurisdiction, and users are responsible for:
						</p>
						<ul>
							<li>Reviewing photos after uploading</li>
							<li>Reporting any failed anonymization or privacy concerns</li>
							<li>Ensuring compliance with local privacy laws</li>
							<li>Respecting others' privacy rights regardless of technical safeguards</li>
						</ul>
					</div>
				</div>

				<p>
					<strong>Reporting Issues:</strong> If you notice any photos that contain unblurred faces,
					license plates, or other identifying information, please report them immediately by using
					the "Flag for review" function on the specific photo. For general privacy concerns, you can
					also contact us through our <a href="/contact" class="legal-link">contact form</a> or
					<a href="https://github.com/koo5/hillview" target="_blank" rel="noopener noreferrer" class="legal-link">
					GitHub repository</a>.
				</p>

		</section>

		<section class="document-section">
			<h2>6. Privacy and Data Protection</h2>
			<p>
				Your privacy is important to us. Our collection and use of personal information is
				governed by our <a href="/privacy" class="legal-link">Privacy Policy</a>, which is
				incorporated into these terms by reference.
			</p>
		</section>

		<section class="document-section">
			<h2>7. Prohibited Uses</h2>
			<p>You agree not to use Hillview to:</p>
			<ul>
				<li>Upload content that is illegal, harmful, or violates others' rights</li>
				<li>Deliberately circumvent or disable privacy protection features</li>
				<li>Upload photos with the intent to identify or track individuals</li>
				<li>Interfere with or disrupt the service or servers</li>
				<li>Attempt to gain unauthorized access to any part of the service</li>
				<li>Use the service for any commercial purpose without our permission</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>8. Intellectual Property</h2>
			<p>
				Hillview and its original content, features, and functionality are owned by the
				Hillview team and are protected by copyright, trademark, and other intellectual
				property laws.
			</p>
		</section>

		<section class="document-section">
			<h2>9. Disclaimer of Warranties</h2>
			<p>
				Hillview is provided "as is" without any warranties, express or implied. We do not
				guarantee that the service will be uninterrupted, secure, or error-free. Location
				and directional information should not be relied upon for navigation or safety purposes.
				<strong>Automatic privacy protection features, while designed to be effective, are not guaranteed
				to catch all identifying information.</strong>
			</p>
		</section>

		<section class="document-section">
			<h2>10. Limitation of Liability</h2>
			<p>
				To the fullest extent permitted by law, Hillview and its developers shall not be
				liable for any indirect, incidental, special, consequential, or punitive damages
				arising from your use of the service, including but not limited to privacy breaches
				resulting from failed anonymization.
			</p>
		</section>

		<section class="document-section">
			<h2>11. Termination</h2>
			<p>
				We may terminate or suspend your account and access to the service at any time,
				without prior notice, for conduct that we believe violates these terms or is
				dangerous or harmful to yourself or other users or the service.
			</p>
		</section>

		<section class="document-section">
			<h2>12. Changes to Terms</h2>
			<p>
				We reserve the right to modify these terms at any time. We will notify users of
				significant changes by posting the new terms on this page. Your continued use of
				the service after changes constitutes acceptance of the new terms.
			</p>
		</section>

		<section class="document-section">
			<h2>13. Contact Information</h2>
			<p>
				If you have questions about these Terms of Service, please contact us:
			</p>
			<ul>
				<li>Through our <a href="/contact" class="legal-link">contact form</a></li>
				<li>Via our <a href="https://github.com/koo5/hillview" target="_blank" rel="noopener noreferrer" class="legal-link">GitHub repository</a></li>
			</ul>
		</section>

		<footer class="document-footer">
			<div class="footer-note">
				<Mail size={16} />
				<span>For questions or privacy concerns, please use our <a href="/contact" class="legal-link">contact form</a> or GitHub repository.</span>
			</div>
		</footer>
	</div>
</StandardBody>

<style>
	.legal-document {
		max-width: 800px;
		margin: 0 auto;
		background: white;
		border-radius: 12px;
		box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
		overflow: hidden;
	}

	.document-header {
		text-align: center;
		padding: 40px 32px;
		background: linear-gradient(135deg, #f8fafc, #e2e8f0);
		border-bottom: 1px solid #e5e7eb;
	}

	.document-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 80px;
		height: 80px;
		background: linear-gradient(135deg, #3b82f6, #1d4ed8);
		border-radius: 20px;
		color: white;
		margin-bottom: 16px;
	}

	.document-header h1 {
		font-size: 2.25rem;
		font-weight: bold;
		color: #1f2937;
		margin: 0 0 16px 0;
	}

	.document-meta {
		display: flex;
		justify-content: center;
		gap: 24px;
		flex-wrap: wrap;
	}

	.meta-item {
		display: flex;
		align-items: center;
		gap: 8px;
		color: #6b7280;
		font-size: 0.875rem;
	}

	.document-section {
		padding: 32px;
		border-bottom: 1px solid #f3f4f6;
	}

	.document-section:last-of-type {
		border-bottom: none;
	}

	.document-section h2 {
		font-size: 1.5rem;
		font-weight: 600;
		color: #1f2937;
		margin: 0 0 16px 0;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.document-section p {
		color: #4b5563;
		line-height: 1.7;
		margin: 0 0 16px 0;
		font-size: 1rem;
	}

	.document-section ul {
		color: #4b5563;
		line-height: 1.7;
		margin: 0 0 16px 0;
		padding-left: 24px;
	}

	.document-section li {
		margin-bottom: 8px;
	}


	.warning-box {
		background: #fef3c7;
		border: 1px solid #f59e0b;
		border-radius: 8px;
		padding: 20px;
		margin: 20px 0;
		display: flex;
		gap: 12px;
	}

	.warning-box > :global(svg) {
		color: #d97706;
		flex-shrink: 0;
		margin-top: 2px;
	}

	.warning-box p {
		margin: 0 0 12px 0;
	}

	.warning-box p:last-child {
		margin-bottom: 0;
	}

	.warning-box ul {
		margin: 12px 0 0 0;
	}

	.legal-link {
		color: #3b82f6;
		text-decoration: underline;
		transition: color 0.2s ease;
	}

	.legal-link:hover {
		color: #1d4ed8;
	}

	.document-footer {
		padding: 24px 32px;
		background: #f8fafc;
		border-top: 1px solid #e5e7eb;
	}

	.footer-note {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		color: #6b7280;
		font-size: 0.875rem;
		text-align: center;
	}

	/* Responsive adjustments */
	@media (max-width: 768px) {
		.legal-document {
			margin: 0;
			border-radius: 0;
		}

		.document-header {
			padding: 32px 24px;
		}

		.document-header h1 {
			font-size: 1.875rem;
		}

		.document-section {
			padding: 24px;
		}


		.warning-box {
			flex-direction: column;
			gap: 8px;
		}

		.document-footer {
			padding: 20px 24px;
		}
	}
</style>
