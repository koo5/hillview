<svelte:head>
	<title>Privacy Policy - Hillview</title>
</svelte:head>

<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import { Shield, Calendar, Mail, Database, Eye, Lock, Users } from 'lucide-svelte';
</script>

<StandardHeaderWithAlert
	title="Privacy Policy"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	<div class="legal-document">
		<header class="document-header">
			<div class="document-icon">
				<Shield size={48} />
			</div>
			<h1>Privacy Policy</h1>
			<div class="document-meta">
				<div class="meta-item">
					<Calendar size={16} />
					<span>Last updated: December 2025</span>
				</div>
			</div>
		</header>

		<section class="document-section">
			<h2>1. Information We Collect</h2>
			<p>
				When you use Hillview, we may collect the following types of information:
			</p>
			<h3>Information we collect on our servers</h3>
			<ul>
				<li><strong>Account Information:</strong> Username, email address, and authentication data</li>
				<li><strong>Photo Data:</strong> Images you upload, including embedded geolocation information, timestamps, and camera settings</li>
			</ul>
			<h3>Information we collect through third-party services</h3>
			<b>For development and troubleshooting, we may also collect:</b>
			<ul>
				<li><strong>Device Information:</strong> Device type, operating system, and app version</li>
				<li><strong>Usage Data:</strong> How you interact with the app and which features you use</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>
				<Eye size={24} />
				2. Automatic Privacy Protection
			</h2>
				<p>
					Hillview implements automatic privacy protection measures to safeguard privacy of individuals appearing in photos:
				</p>
				<ul>
					<li><strong>Face Detection and Blurring:</strong> Human faces are automatically detected and blurred in uploaded photos</li>
					<li><strong>License Plate Obscuring:</strong> Vehicle license plates are automatically detected and made unreadable</li>
					<li><strong>Identifying Feature Processing:</strong> Other potentially identifying elements may be automatically processed</li>
				</ul>

				<div class="limitation-notice">
					<Lock size={20} />
					<div>
						<p><strong>System Limitations:</strong></p>
						<p>
							While our privacy protection systems are designed to be effective, no automated
							system is perfect. Users should be aware that:
						</p>
						<ul>
							<li>Some faces or license plates may not be detected</li>
							<li>New types of identifying information may not be recognized</li>
							<li>Users are encouraged to review photos and use the "Flag for review" function to report specific privacy concerns</li>
						</ul>
					</div>
				</div>
		</section>

		<section class="document-section">
			<h2>
				<Database size={24} />
				3. How We Use Your Information
			</h2>
			<p>We use the information we collect to:</p>
			<ul>
				<li>Provide and maintain the Hillview service</li>
				<li>Process and display your photos with directional data</li>
				<li>Enable location-based features and landmark identification</li>
				<li>Improve our automatic privacy protection systems</li>
				<li>Communicate with you about the service</li>
				<li>Ensure the security and integrity of the platform</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>
				<Users size={24} />
				4. Information Sharing
			</h2>
			<p>We do not sell your personal information. We may share information in the following circumstances:</p>
			<ul>
				<li><strong>Uploaded Photos:</strong> Photos you upload will be visible to other users</li>
				<li><strong>Service Providers:</strong> With trusted service providers who help us operate the service</li>
				<li><strong>Legal Requirements:</strong> When required by law or to protect our rights and users' safety</li>
				<li><strong>Business Transfers:</strong> In connection with a merger, acquisition, or sale of assets</li>
			</ul>

			<div class="sharing-notice">
				<p><strong>Public Photo Considerations:</strong></p>
				<p>
					When you upload photos, they become visible to other Hillview users.
					Even with automatic privacy protection, consider whether you want to share
					photos taken near your home, workplace, or other sensitive locations.
				</p>
			</div>
		</section>

		<section class="document-section">
			<h2>5. Data Security</h2>
			<p>
				We implement appropriate technical and organizational measures to protect your
				personal information against unauthorized access, alteration, disclosure, or destruction.
				These measures include:
			</p>
			<ul>
				<li>Encryption of data in transit</li>
				<li>Regular security assessments and updates</li>
				<li>Access controls and authentication systems</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>6. Your Rights and Choices</h2>
			<p>You have the following rights regarding your personal information:</p>
			<ul>
				<li><strong>Access:</strong> Request access to your personal data</li>
				<li><strong>Correction:</strong> Request correction of inaccurate data</li>
				<li><strong>Deletion:</strong> Request deletion of your account and associated data</li>
				<li><strong>Data Portability:</strong> Request a copy of your data in a portable format</li>
				<li><strong>Photo Management:</strong> Manage or delete your uploaded photos</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>7. Data Retention</h2>
			<p>
				We retain your personal information for as long as necessary to provide the service
				and fulfill the purposes outlined in this policy. When you delete your account:
			</p>
			<ul>
				<li>Your account information is permanently deleted</li>
				<li>Your uploaded photos are removed from public view</li>
				<li>Some anonymized usage data may be retained for service improvement</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>8. Third-Party Services</h2>
			<p>
				Hillview may integrate with third-party services for authentication (OAuth providers)
				and mapping data. These services have their own privacy policies:
			</p>
			<ul>
				<li>OAuth providers (Google, GitHub) for account authentication</li>
				<li>Map tile providers for displaying maps</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>9. Children's Privacy</h2>
			<p>
				Hillview is not intended for children under 13 years of age. We do not knowingly
				collect personal information from children under 13. If you become aware that a
				child has provided us with personal information, please contact us.
			</p>
		</section>

		<section class="document-section">
			<h2>10. International Data Transfers</h2>
			<p>
				Your information may be transferred to and processed in countries other than your
				country of residence. We ensure appropriate safeguards are in place to protect
				your personal information when it is transferred.
			</p>
		</section>

		<section class="document-section">
			<h2>11. Changes to This Policy</h2>
			<p>
				We may update this Privacy Policy from time to time. We will notify you of any
				material changes by posting the new policy on this page and updating the "Last updated"
				date. Your continued use of the service constitutes acceptance of the updated policy.
			</p>
		</section>

		<section class="document-section">
			<h2>12. Contact Us</h2>
			<p>
				If you have questions about this Privacy Policy or our privacy practices, please contact us:
			</p>
			<ul>
				<li>Use the "Flag for review" function on specific photos for failed anonymization reports</li>
				<li>Through our <a href="/contact" class="legal-link">contact form</a> for general privacy questions</li>
				<li>Via our <a href="https://github.com/koo5/hillview" target="_blank" rel="noopener noreferrer" class="legal-link">GitHub repository</a> for technical issues</li>
			</ul>
		</section>

		<footer class="document-footer">
			<div class="footer-note">
				<Mail size={16} />
				<span>Use "Flag for review" on photos for anonymization issues, or our <a href="/contact" class="legal-link">contact form</a> for general privacy questions.</span>
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
		background: linear-gradient(135deg, #f0f9ff, #dbeafe);
		border-bottom: 1px solid #e5e7eb;
	}

	.document-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 80px;
		height: 80px;
		background: linear-gradient(135deg, #10b981, #059669);
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

	.privacy-features {
		background: #f0fdf4;
		border: 2px solid #bbf7d0;
		border-radius: 8px;
		margin: 16px 0;
	}

	.privacy-notice {
		background: white;
		padding: 24px;
		border-radius: 6px;
		border: 1px solid #d1fae5;
	}

	.limitation-notice {
		background: #fef3c7;
		border: 1px solid #f59e0b;
		border-radius: 8px;
		padding: 20px;
		margin: 20px 0;
		display: flex;
		gap: 12px;
	}

	.limitation-notice > :global(svg) {
		color: #d97706;
		flex-shrink: 0;
		margin-top: 2px;
	}

	.limitation-notice p {
		margin: 0 0 12px 0;
	}

	.limitation-notice p:last-child {
		margin-bottom: 0;
	}

	.limitation-notice ul {
		margin: 12px 0 0 0;
	}

	.sharing-notice {
		background: #eff6ff;
		border: 1px solid #3b82f6;
		border-radius: 8px;
		padding: 16px;
		margin: 16px 0;
	}

	.sharing-notice p {
		margin: 0 0 8px 0;
		color: #1e40af;
	}

	.sharing-notice p:last-child {
		margin-bottom: 0;
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

		.privacy-notice {
			padding: 20px;
		}

		.limitation-notice {
			flex-direction: column;
			gap: 8px;
		}

		.document-footer {
			padding: 20px 24px;
		}
	}
</style>
