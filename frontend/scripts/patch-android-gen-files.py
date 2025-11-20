#!/usr/bin/env python3
"""
Android Generated Files Patcher

Idempotent script to patch Android generated files for Tauri Android builds.
Fixes manifest issues, configures signing, and applies necessary patches.
Uses proper XML parsing and references external keystore.properties file.

Usage: python3 scripts/patch-android-gen-files.py
"""

import os
import sys
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import re
from pathlib import Path
from typing import Optional


class AndroidConfigurer:
	def __init__(self, project_root: Path):
		self.project_root = project_root
		self.android_root = project_root / "src-tauri" / "gen" / "android"
		self.manifest_file = self.android_root / "app" / "src" / "main" / "AndroidManifest.xml"
		self.build_gradle_file = self.android_root / "app" / "build.gradle.kts"
		self.root_build_gradle_file = self.android_root / "build.gradle.kts"
		self.buildsrc_build_gradle_file = self.android_root / "buildSrc" / "build.gradle.kts"
		self.gradle_properties_file = self.android_root / "gradle.properties"
		self.plugin_build_gradle_file = project_root / "tauri-plugin-hillview" / "android" / "build.gradle.kts"
		self.colors_file = self.android_root / "app" / "src" / "main" / "res" / "values" / "colors.xml"
		self.gitignore_file = project_root / ".gitignore"

		# External keystore configuration (maintained by user)
		self.keystore_props_path = Path.home() / "secrets" / "keystore.properties"

		# Google Services configuration paths
		self.google_services_target = self.android_root / "app" / "google-services.json"

	def log(self, message: str, level: str = "INFO"):
		"""Simple logging with color codes"""
		colors = {
			"INFO": "\033[94m",    # Blue
			"SUCCESS": "\033[92m", # Green
			"WARNING": "\033[93m", # Yellow
			"ERROR": "\033[91m",   # Red
			"RESET": "\033[0m"     # Reset
		}
		color = colors.get(level, colors["INFO"])
		print(f"{color}[{level}]{colors['RESET']} {message}")

	def check_prerequisites(self) -> bool:
		"""Check if Android project exists"""
		if not self.android_root.exists():
			self.log(f"Android project not found at {self.android_root}", "ERROR")
			self.log("Run: ./scripts/tauri-android.sh android init", "WARNING")
			return False

		if not self.manifest_file.exists():
			self.log(f"AndroidManifest.xml not found at {self.manifest_file}", "ERROR")
			return False

		if not self.build_gradle_file.exists():
			self.log(f"build.gradle.kts not found at {self.build_gradle_file}", "ERROR")
			return False

		# Check for external keystore.properties
		if not self.keystore_props_path.exists():
			self.log(f"External keystore.properties not found at {self.keystore_props_path}", "WARNING")
			self.log("Please create ~/secrets/keystore.properties with your keystore configuration", "WARNING")
		else:
			self.log(f"External keystore.properties found at {self.keystore_props_path}", "SUCCESS")

		return True

	def fix_android_manifest(self) -> bool:
		"""Fix AndroidManifest.xml using proper XML DOM parsing"""
		self.log("Fixing AndroidManifest.xml...")

		try:
			tools_ns = "http://schemas.android.com/tools"
			android_ns = "http://schemas.android.com/apk/res/android"

			# Use minidom for proper DOM manipulation
			try:
				with open(self.manifest_file, 'r', encoding='utf-8') as f:
					dom = minidom.parse(f)
				self.log("XML parsed successfully with DOM", "SUCCESS")
			except Exception as pe:
				self.log(f"DOM parse error: {pe}", "ERROR")
				return False

			# Get the manifest element
			manifest_elem = dom.documentElement
			if manifest_elem.tagName != "manifest":
				raise Exception("Root element is not manifest")

			changes_made = False

			# Check and fix namespace declarations
			android_ns_attr = "xmlns:android"
			tools_ns_attr = "xmlns:tools"

			# Handle android namespace
			if not manifest_elem.hasAttribute(android_ns_attr):
				manifest_elem.setAttribute(android_ns_attr, android_ns)
				changes_made = True
				self.log("Added android namespace", "SUCCESS")
			elif manifest_elem.getAttribute(android_ns_attr) != android_ns:
				manifest_elem.setAttribute(android_ns_attr, android_ns)
				changes_made = True
				self.log("Fixed android namespace", "SUCCESS")

			# Handle tools namespace
			if not manifest_elem.hasAttribute(tools_ns_attr):
				manifest_elem.setAttribute(tools_ns_attr, tools_ns)
				changes_made = True
				self.log("Added tools namespace", "SUCCESS")
			elif manifest_elem.getAttribute(tools_ns_attr) != tools_ns:
				manifest_elem.setAttribute(tools_ns_attr, tools_ns)
				changes_made = True
				self.log("Fixed tools namespace", "SUCCESS")

			# Ensure storage permissions are present
			required_permissions = [
				"android.permission.WRITE_EXTERNAL_STORAGE",
				"android.permission.READ_EXTERNAL_STORAGE"
			]

			for permission in required_permissions:
				# Check if permission already exists
				permission_exists = False
				for perm_elem in manifest_elem.getElementsByTagName("uses-permission"):
					if perm_elem.hasAttribute("android:name") and perm_elem.getAttribute("android:name") == permission:
						permission_exists = True
						break

				if not permission_exists:
					# Create new uses-permission element
					perm_elem = dom.createElement("uses-permission")
					perm_elem.setAttribute("android:name", permission)

					# Insert before application element if it exists, otherwise at end
					app_elements = manifest_elem.getElementsByTagName("application")
					if app_elements:
						manifest_elem.insertBefore(perm_elem, app_elements[0])
					else:
						manifest_elem.appendChild(perm_elem)

					changes_made = True
					self.log(f"Added permission: {permission}", "SUCCESS")
				else:
					self.log(f"Permission already present: {permission}", "SUCCESS")

			# Find application element
			app_elements = manifest_elem.getElementsByTagName("application")
			if app_elements:
				app_elem = app_elements[0]
				tools_replace_attr = "tools:replace"

				# Check tools:replace attribute
				if not app_elem.hasAttribute(tools_replace_attr):
					app_elem.setAttribute(tools_replace_attr, "android:usesCleartextTraffic")
					changes_made = True
					self.log("Added tools:replace attribute", "SUCCESS")
				else:
					current_replace = app_elem.getAttribute(tools_replace_attr)
					replace_items = set(item.strip() for item in current_replace.split(",") if item.strip())

					if "android:usesCleartextTraffic" not in replace_items:
						replace_items.add("android:usesCleartextTraffic")
						new_replace = ",".join(sorted(replace_items))
						app_elem.setAttribute(tools_replace_attr, new_replace)
						changes_made = True
						self.log("Updated tools:replace attribute", "SUCCESS")
					else:
						self.log("tools:replace already configured correctly", "SUCCESS")
			else:
				self.log("Warning: No application element found", "WARNING")

			# Add deep-link intent filters to MainActivity
			main_activity = self._find_main_activity(manifest_elem)
			if main_activity:
				if self._add_deep_link_intent_filters(dom, main_activity):
					changes_made = True
			else:
				self.log("Warning: MainActivity not found for deep-link configuration", "WARNING")

			# Add FCM and UnifiedPush services
			if self._add_push_services(dom, app_elem if app_elements else None):
				changes_made = True

			# Write back only if changes were made
			if changes_made:
				# Write with proper formatting
				with open(self.manifest_file, 'w', encoding='utf-8') as f:
					dom.writexml(f, encoding='utf-8', addindent='    ', newl='\n')
				self.log(f"wrote {self.manifest_file}", "INFO")
				self.log("AndroidManifest.xml updated successfully", "SUCCESS")
			else:
				self.log("AndroidManifest.xml already correctly configured", "SUCCESS")

			return True

		except Exception as e:
			self.log(f"Error fixing AndroidManifest.xml: {e}", "ERROR")
			return False

	def _find_main_activity(self, manifest_elem):
		"""Find the MainActivity element in the manifest"""
		for activity in manifest_elem.getElementsByTagName("activity"):
			name_attr = activity.getAttribute("android:name")
			# Look for MainActivity (could be fully qualified or relative)
			if name_attr and ("MainActivity" in name_attr or name_attr.endswith(".MainActivity")):
				return activity
		return None

	def _add_deep_link_intent_filters(self, dom, main_activity):
		"""Add deep-link intent filters to MainActivity if not already present"""
		changes_made = False

		# Check if deep-link intent filters already exist
		existing_schemes = set()
		for intent_filter in main_activity.getElementsByTagName("intent-filter"):
			for data_elem in intent_filter.getElementsByTagName("data"):
				scheme = data_elem.getAttribute("android:scheme")
				if scheme:
					existing_schemes.add(scheme)

		# Determine scheme based on DEV_MODE environment variable
		dev_mode_str = os.environ.get('DEV_MODE', 'false')
		is_dev_mode = dev_mode_str == 'true'
		scheme = "cz.hillviedev" if is_dev_mode else "cz.hillview"
		required_schemes = [scheme]

		self.log(f"DEV_MODE='{dev_mode_str}', using scheme: {scheme}", "INFO")

		for scheme in required_schemes:
			if scheme not in existing_schemes:
				# Create new intent-filter for this scheme
				intent_filter = dom.createElement("intent-filter")

				# Add action
				action = dom.createElement("action")
				action.setAttribute("android:name", "android.intent.action.VIEW")
				intent_filter.appendChild(action)

				# Add categories
				default_category = dom.createElement("category")
				default_category.setAttribute("android:name", "android.intent.category.DEFAULT")
				intent_filter.appendChild(default_category)

				browsable_category = dom.createElement("category")
				browsable_category.setAttribute("android:name", "android.intent.category.BROWSABLE")
				intent_filter.appendChild(browsable_category)

				# Add data with scheme
				data_elem = dom.createElement("data")
				data_elem.setAttribute("android:scheme", scheme)
				intent_filter.appendChild(data_elem)

				# Add intent-filter to main activity
				main_activity.appendChild(intent_filter)
				changes_made = True
				self.log(f"Added deep-link intent filter for scheme: {scheme}", "SUCCESS")
			else:
				self.log(f"Deep-link intent filter already exists for scheme: {scheme}", "SUCCESS")

		return changes_made

	def _add_push_services(self, dom, app_elem):
		"""Add FCM and UnifiedPush services to the application element"""
		if not app_elem:
			self.log("No application element found for push services", "WARNING")
			return False

		changes_made = False

		# Define the services we need
		services_to_add = [
			{
				"name": "cz.hillview.plugin.HillviewUnifiedPushService",
				"exported": "false",
				"intent_filters": [
					{
						"actions": [
							"org.unifiedpush.android.connector.MESSAGE",
							"org.unifiedpush.android.connector.UNREGISTERED",
							"org.unifiedpush.android.connector.NEW_ENDPOINT",
							"org.unifiedpush.android.connector.REGISTRATION_FAILED"
						]
					}
				]
			},
			{
				"name": "cz.hillview.plugin.FcmDirectService",
				"exported": "false",
				"intent_filters": [
					{
						"actions": ["com.google.firebase.MESSAGING_EVENT"]
					}
				]
			}
		]

		# Check for existing services and add missing ones
		existing_services = set()
		for service in app_elem.getElementsByTagName("service"):
			name_attr = service.getAttribute("android:name")
			if name_attr:
				existing_services.add(name_attr)

		for service_config in services_to_add:
			service_name = service_config["name"]
			if service_name not in existing_services:
				# Create service element
				service_elem = dom.createElement("service")
				service_elem.setAttribute("android:name", service_name)
				service_elem.setAttribute("android:exported", service_config["exported"])

				# Add intent filters
				for intent_filter_config in service_config["intent_filters"]:
					intent_filter = dom.createElement("intent-filter")

					for action_name in intent_filter_config["actions"]:
						action = dom.createElement("action")
						action.setAttribute("android:name", action_name)
						intent_filter.appendChild(action)

					service_elem.appendChild(intent_filter)

				# Add service to application element
				app_elem.appendChild(service_elem)
				changes_made = True
				self.log(f"Added push service: {service_name}", "SUCCESS")
			else:
				self.log(f"Push service already exists: {service_name}", "SUCCESS")

		return changes_made

	def _indent_xml(self, elem, level=0):
		"""Add pretty-printing indentation to XML"""
		i = "\n" + level * "    "
		if len(elem):
			if not elem.text or not elem.text.strip():
				elem.text = i + "    "
			if not elem.tail or not elem.tail.strip():
				elem.tail = i
			for child in elem:
				self._indent_xml(child, level + 1)
			if not child.tail or not child.tail.strip():
				child.tail = i
		else:
			if level and (not elem.tail or not elem.tail.strip()):
				elem.tail = i

	def configure_build_gradle(self) -> bool:
		"""Configure build.gradle.kts for signing with external keystore.properties"""
		self.log("Configuring build.gradle.kts for signing...")

		try:
			content = self.build_gradle_file.read_text()
			original_content = content

			# Check and add FileInputStream import
			if "import java.io.FileInputStream" not in content:
				# Add after existing imports
				import_pattern = r"(import java\.util\.Properties.*?\n)"
				replacement = r"\1import java.io.FileInputStream\n"
				content = re.sub(import_pattern, replacement, content)
				self.log("Added FileInputStream import", "SUCCESS")
			else:
				self.log("FileInputStream import already present", "SUCCESS")

			# Check if signingConfigs block exists
			if "signingConfigs" not in content:
				self.log("Adding signing configuration...", "INFO")

				# Find the position after defaultConfig block
				pattern = r"(\s+defaultConfig\s*\{[^}]*\}\s*)"

				# Use external keystore.properties path
				signing_config = f'''
	signingConfigs {{
		create("release") {{
			val keystorePropertiesFile = file("{self.keystore_props_path}")
			val keystoreProperties = Properties()
			if (keystorePropertiesFile.exists()) {{
				keystoreProperties.load(FileInputStream(keystorePropertiesFile))

				keyAlias = keystoreProperties["keyAlias"] as String
				keyPassword = keystoreProperties["password"] as String
				storeFile = file(keystoreProperties["storeFile"] as String)
				storePassword = keystoreProperties["password"] as String
			}}
		}}
	}}
'''

				replacement = r"\1" + signing_config
				content = re.sub(pattern, replacement, content, flags=re.DOTALL)
				self.log("Added signing configuration with external keystore.properties", "SUCCESS")
			else:
				self.log("Signing configuration already present", "SUCCESS")

			# Check if release buildType uses signing config
			release_pattern = r'getByName\("release"\)\s*\{([^}]*)\}'
			release_match = re.search(release_pattern, content, re.DOTALL)

			if release_match and "signingConfig" not in release_match.group(1):
				self.log("Adding signingConfig to release buildType...", "INFO")

				# Find the release block and add signing config
				release_content = release_match.group(1)
				new_release_content = release_content.rstrip() + '\n            signingConfig = signingConfigs.getByName("release")\n        '

				content = content.replace(release_match.group(0),
					f'getByName("release") {{{new_release_content}}}')
				self.log("Added signingConfig to release buildType", "SUCCESS")
			else:
				self.log("Release buildType already configured for signing", "SUCCESS")

			# Write back if changes were made
			if content != original_content:
				self.build_gradle_file.write_text(content)
				self.log("build.gradle.kts updated successfully", "SUCCESS")

			return True

		except Exception as e:
			self.log(f"Error configuring build.gradle.kts: {e}", "ERROR")
			return False

	def patch_colors_xml(self) -> bool:
		"""Patch colors.xml with hillview colors using XML parsing"""
		self.log("Patching colors.xml...")

		if not self.colors_file.exists():
			self.log(f"colors.xml not found at {self.colors_file}", "WARNING")
			return True

		try:
			tree = ET.parse(self.colors_file)
			root = tree.getroot()
			changes_made = False

			# Define our hillview color mappings
			hillview_colors = {
				'hillview_green': '#8BC34A',
				'hillview_green_dark': '#689F38',
				'hillview_green_light': '#DCEDC8',
				'hillview_accent': '#4CAF50',
				'hillview_accent_dark': '#388E3C'
			}

			# Update existing color elements or add if missing
			for color_name, color_value in hillview_colors.items():
				color_elem = root.find(f".//color[@name='{color_name}']")
				if color_elem is not None:
					if color_elem.text != color_value:
						color_elem.text = color_value
						changes_made = True
						self.log(f"Updated {color_name} to {color_value}", "SUCCESS")
				else:
					# Add missing color
					new_color = ET.SubElement(root, 'color')
					new_color.set('name', color_name)
					new_color.text = color_value
					changes_made = True
					self.log(f"Added {color_name}: {color_value}", "SUCCESS")

			if changes_made:
				tree.write(self.colors_file, encoding='utf-8', xml_declaration=True)
				self.log("colors.xml updated successfully", "SUCCESS")
			else:
				self.log("colors.xml already has correct values", "SUCCESS")

			return True

		except Exception as e:
			self.log(f"Error patching colors.xml: {e}", "ERROR")
			return False

	def fix_kotlin_versions(self) -> bool:
		"""Fix Kotlin version compatibility issues in generated files"""
		self.log("Fixing Kotlin version compatibility...")

		success = True

		# Fix root build.gradle.kts
		if not self._fix_root_build_gradle():
			success = False

		# Fix buildSrc build.gradle.kts
		if not self._fix_buildsrc_build_gradle():
			success = False

		# Fix root build.gradle.kts for Google Services
		if not self._add_google_services_to_root():
			success = False

		# Fix gradle.properties
		if not self._fix_gradle_properties():
			success = False

		# Fix app build.gradle.kts
		if not self._fix_app_build_gradle():
			success = False

		# Fix plugin build.gradle.kts
		if not self._fix_plugin_build_gradle():
			success = False

		return success

	def _fix_root_build_gradle(self) -> bool:
		"""Fix root build.gradle.kts Kotlin version"""
		if not self.root_build_gradle_file.exists():
			self.log(f"Root build.gradle.kts not found at {self.root_build_gradle_file}", "WARNING")
			return True

		try:
			content = self.root_build_gradle_file.read_text()
			original_content = content

			# Update Kotlin version to 2.0.20 for compatibility
			kotlin_pattern = r'classpath\("org\.jetbrains\.kotlin:kotlin-gradle-plugin:[\d\.]+"\)'
			new_kotlin = 'classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.0.20")'

			if re.search(kotlin_pattern, content):
				content = re.sub(kotlin_pattern, new_kotlin, content)
				self.log("Updated Kotlin gradle plugin to 2.0.20", "SUCCESS")
			else:
				self.log("Kotlin gradle plugin version not found", "WARNING")

			if content != original_content:
				self.root_build_gradle_file.write_text(content)

			return True

		except Exception as e:
			self.log(f"Error fixing root build.gradle.kts: {e}", "ERROR")
			return False

	def _add_google_services_to_root(self) -> bool:
		"""Add Google Services plugin to root build.gradle.kts"""
		if not self.root_build_gradle_file.exists():
			self.log(f"Root build.gradle.kts not found at {self.root_build_gradle_file}", "WARNING")
			return True

		try:
			content = self.root_build_gradle_file.read_text()
			original_content = content

			# Check if Google Services plugin is already in dependencies
			if 'com.google.gms.google-services' not in content:
				# Find the dependencies block and add Google Services plugin
				deps_pattern = r'(dependencies\s*\{[^}]*)(classpath\("org\.jetbrains\.kotlin:kotlin-gradle-plugin:[^"]+"\))([^}]*\})'
				if re.search(deps_pattern, content, re.DOTALL):
					replacement = r'\1\2\n        classpath("com.google.gms:google-services:4.4.0")\3'
					content = re.sub(deps_pattern, replacement, content, flags=re.DOTALL)
					self.log("Added Google Services plugin to root build dependencies", "SUCCESS")
				else:
					self.log("Could not find dependencies block to add Google Services plugin", "WARNING")
			else:
				# Update existing version to stable working version
				content = re.sub(r'com\.google\.gms:google-services:[\d\.]+', 'com.google.gms:google-services:4.4.0', content)
				self.log("Updated Google Services plugin to version 4.4.0", "SUCCESS")

			if content != original_content:
				self.root_build_gradle_file.write_text(content)

			return True

		except Exception as e:
			self.log(f"Error adding Google Services to root build.gradle.kts: {e}", "ERROR")
			return False

	def _fix_buildsrc_build_gradle(self) -> bool:
		"""Fix buildSrc build.gradle.kts to ensure Kotlin DSL version consistency"""
		if not self.buildsrc_build_gradle_file.exists():
			self.log(f"buildSrc build.gradle.kts not found at {self.buildsrc_build_gradle_file}", "WARNING")
			return True

		try:
			content = self.buildsrc_build_gradle_file.read_text()
			original_content = content

			# Add explicit Kotlin version to buildSrc dependencies
			if "org.jetbrains.kotlin:kotlin-gradle-plugin" not in content:
				# Add Kotlin plugin dependency after the existing dependencies
				deps_pattern = r'(dependencies\s*\{[^}]*)(implementation\("com\.android\.tools\.build:gradle:[^"]+"\))([^}]*\})'
				if re.search(deps_pattern, content, re.DOTALL):
					replacement = r'\1\2\n    implementation("org.jetbrains.kotlin:kotlin-gradle-plugin:2.0.20")\3'
					content = re.sub(deps_pattern, replacement, content, flags=re.DOTALL)
					self.log("Added Kotlin gradle plugin to buildSrc dependencies", "SUCCESS")
			else:
				self.log("Kotlin gradle plugin already in buildSrc dependencies", "SUCCESS")

			if content != original_content:
				self.buildsrc_build_gradle_file.write_text(content)

			return True

		except Exception as e:
			self.log(f"Error fixing buildSrc build.gradle.kts: {e}", "ERROR")
			return False

	def _fix_gradle_properties(self) -> bool:
		"""Fix gradle.properties to suppress warnings"""
		if not self.gradle_properties_file.exists():
			self.log(f"gradle.properties not found at {self.gradle_properties_file}", "WARNING")
			return True

		try:
			content = self.gradle_properties_file.read_text()
			original_content = content

			# Add suppressUnsupportedCompileSdk if not present
			suppress_compile_sdk = "android.suppressUnsupportedCompileSdk=36"
			if suppress_compile_sdk not in content:
				content = content.rstrip() + "\n" + suppress_compile_sdk + "\n"
				self.log("Added suppressUnsupportedCompileSdk=36", "SUCCESS")

			# Add Java compile deprecation warning suppression
			suppress_java_deprecation = "android.javaCompile.suppressSourceTargetDeprecationWarning=true"
			if suppress_java_deprecation not in content:
				content = content.rstrip() + "\n" + suppress_java_deprecation + "\n"
				self.log("Added suppressSourceTargetDeprecationWarning=true", "SUCCESS")

			if content != original_content:
				self.gradle_properties_file.write_text(content)

			return True

		except Exception as e:
			self.log(f"Error fixing gradle.properties: {e}", "ERROR")
			return False

	def _fix_app_build_gradle(self) -> bool:
		"""Fix app build.gradle.kts to force Kotlin versions"""
		if not self.build_gradle_file.exists():
			self.log(f"App build.gradle.kts not found at {self.build_gradle_file}", "ERROR")
			return False

		try:
			content = self.build_gradle_file.read_text()
			original_content = content

			# Add version forcing if not present
			version_forcing = '''configurations.all {
    resolutionStrategy {
        force("org.jetbrains.kotlin:kotlin-stdlib:2.0.20")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk8:2.0.20")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk7:2.0.20")
        force("org.jetbrains.kotlin:kotlin-reflect:2.0.20")
    }
}'''

			if "configurations.all" not in content:
				# Find position after rust block
				rust_pattern = r'(rust\s*\{[^}]*\}\s*)'
				if re.search(rust_pattern, content, re.DOTALL):
					replacement = r'\1\n' + version_forcing + '\n\n'
					content = re.sub(rust_pattern, replacement, content, flags=re.DOTALL)
					self.log("Added Kotlin version forcing to app build.gradle.kts", "SUCCESS")
				else:
					self.log("Could not find rust block to insert version forcing", "WARNING")
			else:
				self.log("Version forcing already present in app build.gradle.kts", "SUCCESS")

			# Ensure kotlinOptions.jvmTarget is set in app build.gradle.kts
			if "kotlinOptions" not in content:
				# Add kotlinOptions block after compileOptions
				compile_options_pattern = r'(compileOptions\s*\{[^}]*\}\s*)'
				kotlin_options_block = '''    kotlinOptions {
        jvmTarget = "1.8"
    }
'''
				if re.search(compile_options_pattern, content, re.DOTALL):
					replacement = r'\1' + kotlin_options_block
					content = re.sub(compile_options_pattern, replacement, content, flags=re.DOTALL)
					self.log("Added kotlinOptions with jvmTarget 1.8 to app", "SUCCESS")
			else:
				# Update existing kotlinOptions to ensure jvmTarget is 1.8
				kotlin_options_pattern = r'kotlinOptions\s*\{[^}]*\}'
				kotlin_options_replacement = '''kotlinOptions {
        jvmTarget = "1.8"
    }'''
				if re.search(kotlin_options_pattern, content, re.DOTALL):
					content = re.sub(kotlin_options_pattern, kotlin_options_replacement, content, flags=re.DOTALL)
					self.log("Fixed kotlinOptions jvmTarget to 1.8 in app", "SUCCESS")

			# Add conditional Google Services plugin application to app build.gradle.kts
			conditional_plugin_text = 'if (file("google-services.json").exists())'
			if conditional_plugin_text not in content:
				# Remove any unconditional Google Services plugin from plugins block
				if 'id("com.google.gms.google-services")' in content:
					google_services_pattern = r'\s*id\("com\.google\.gms\.google-services"\)[^\n]*\n?'
					content = re.sub(google_services_pattern, '', content)
					self.log("Removed unconditional Google Services plugin from plugins block", "SUCCESS")

				# Add conditional application at the end of file
				conditional_plugin = '''
// Apply Google Services plugin only if google-services.json exists
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}'''

				# Find the end of the file (before any existing conditional plugin)
				if 'apply(from = "tauri.build.gradle.kts")' in content:
					# Add after the tauri apply statement
					tauri_apply_pattern = r'(apply\(from = "tauri\.build\.gradle\.kts"\))'
					replacement = r'\1' + conditional_plugin
					content = re.sub(tauri_apply_pattern, replacement, content)
					self.log("Added conditional Google Services plugin to app build.gradle.kts", "SUCCESS")
				else:
					# Add at the very end
					content = content.rstrip() + conditional_plugin + '\n'
					self.log("Added conditional Google Services plugin at end of app build.gradle.kts", "SUCCESS")
			else:
				self.log("Conditional Google Services plugin already present in app build.gradle.kts", "SUCCESS")

			if content != original_content:
				self.build_gradle_file.write_text(content)

			return True

		except Exception as e:
			self.log(f"Error fixing app build.gradle.kts: {e}", "ERROR")
			return False

	def _fix_plugin_build_gradle(self) -> bool:
		"""Fix plugin build.gradle.kts for Kotlin 2.x compatibility and add Firebase dependencies"""
		if not self.plugin_build_gradle_file.exists():
			self.log(f"Plugin build.gradle.kts not found at {self.plugin_build_gradle_file}", "WARNING")
			return True

		try:
			content = self.plugin_build_gradle_file.read_text()
			original_content = content

			# Update Kotlin serialization plugin version
			serialization_pattern = r'id\("org\.jetbrains\.kotlin\.plugin\.serialization"\) version "[\d\.]+"\)?'
			new_serialization = 'id("org.jetbrains.kotlin.plugin.serialization") version "2.0.20"'

			if re.search(serialization_pattern, content):
				content = re.sub(serialization_pattern, new_serialization, content)
				self.log("Updated Kotlin serialization plugin to 2.0.20", "SUCCESS")

			# Remove Google Services plugin if present (it should only be in root build.gradle.kts)
			if 'id("com.google.gms.google-services")' in content:
				# Remove the Google Services plugin line
				google_services_pattern = r'\s*id\("com\.google\.gms\.google-services"\)[^\n]*\n?'
				content = re.sub(google_services_pattern, '', content)
				self.log("Removed Google Services plugin from plugin build.gradle.kts (should only be in root)", "SUCCESS")
			else:
				self.log("Google Services plugin correctly not present in plugin build.gradle.kts", "SUCCESS")

			# Add Firebase dependencies (using stable versions that resolve correctly)
			firebase_deps = [
				'implementation(platform("com.google.firebase:firebase-bom:32.7.0"))',
				'implementation("com.google.firebase:firebase-messaging-ktx")'
			]

			firebase_missing = []
			for dep in firebase_deps:
				if dep not in content:
					firebase_missing.append(dep)

			if firebase_missing:
				# Find the position after UnifiedPush dependency to add Firebase deps
				unifiedpush_pattern = r'(implementation\("org\.unifiedpush\.android:connector:[^"]+"\))'
				if re.search(unifiedpush_pattern, content):
					firebase_block = '\n\n    // Firebase Cloud Messaging for direct FCM support\n    ' + '\n    '.join(firebase_missing)
					replacement = r'\1' + firebase_block
					content = re.sub(unifiedpush_pattern, replacement, content)
					self.log(f"Added Firebase dependencies: {len(firebase_missing)} items", "SUCCESS")
				else:
					self.log("Could not find position to add Firebase dependencies", "WARNING")
			else:
				self.log("All Firebase dependencies already present", "SUCCESS")

			# Update forced Kotlin versions
			for version in ["1.9.25", "2.0.21", "2.2.0"]:
				content = content.replace(f'kotlin-stdlib:{version}"', 'kotlin-stdlib:2.0.20"')
				content = content.replace(f'kotlin-stdlib-jdk8:{version}"', 'kotlin-stdlib-jdk8:2.0.20"')
				content = content.replace(f'kotlin-stdlib-jdk7:{version}"', 'kotlin-stdlib-jdk7:2.0.20"')
				content = content.replace(f'kotlin-reflect:{version}"', 'kotlin-reflect:2.0.20"')

			# Fix KAPT arguments block for Kotlin 2.x compatibility
			kapt_block_pattern = r'kapt\s*\{[^}]*arguments\s*\{[^}]*\}[^}]*correctErrorTypes\s*=\s*true[^}]*\}'
			kapt_new_block = '''kapt {
    arguments {
        arg("room.schemaLocation", "$projectDir/schemas")
    }
    correctErrorTypes = true
}'''

			if re.search(kapt_block_pattern, content, re.DOTALL):
				content = re.sub(kapt_block_pattern, kapt_new_block, content, flags=re.DOTALL)
				self.log("Fixed KAPT arguments block for Kotlin 2.x", "SUCCESS")

			# Ensure kotlinOptions.jvmTarget is set correctly
			if "kotlinOptions" not in content:
				# Add kotlinOptions block after compileOptions
				compile_options_pattern = r'(compileOptions\s*\{[^}]*\}\s*)'
				kotlin_options_block = '''    kotlinOptions {
        jvmTarget = "1.8"
    }
'''
				if re.search(compile_options_pattern, content, re.DOTALL):
					replacement = r'\1' + kotlin_options_block
					content = re.sub(compile_options_pattern, replacement, content, flags=re.DOTALL)
					self.log("Added kotlinOptions with jvmTarget 1.8", "SUCCESS")
			else:
				# Update existing kotlinOptions to ensure jvmTarget is 1.8
				kotlin_options_pattern = r'kotlinOptions\s*\{[^}]*\}'
				kotlin_options_replacement = '''kotlinOptions {
        jvmTarget = "1.8"
    }'''
				if re.search(kotlin_options_pattern, content, re.DOTALL):
					content = re.sub(kotlin_options_pattern, kotlin_options_replacement, content, flags=re.DOTALL)
					self.log("Fixed kotlinOptions jvmTarget to 1.8", "SUCCESS")

			if content != original_content:
				self.plugin_build_gradle_file.write_text(content)
				self.log("Updated plugin with Kotlin 2.0.20 and Firebase dependencies", "SUCCESS")

			return True

		except Exception as e:
			self.log(f"Error fixing plugin build.gradle.kts: {e}", "ERROR")
			return False

	def copy_google_services_json(self) -> bool:
		"""Copy google-services.json from source directory based on DEV_MODE"""
		self.log("Copying google-services.json...")

		# Determine package based on DEV_MODE environment variable
		dev_mode_str = os.environ.get('DEV_MODE', 'false')
		is_dev_mode = dev_mode_str == 'true'
		package_name = "cz.hillviedev" if is_dev_mode else "cz.hillview"

		# Source path: ../../{package_name}/google-services.json
		source_path = self.project_root / ".." / ".." / package_name / "google-services.json"

		self.log(f"DEV_MODE='{dev_mode_str}', using package: {package_name}", "INFO")
		self.log(f"Looking for google-services.json at: {source_path}", "INFO")

		try:
			if not source_path.exists():
				self.log(f"Google services file not found at {source_path}", "WARNING")
				self.log("FCM will not be available - app will use UnifiedPush only", "WARNING")
				return True  # Not a fatal error, just means no FCM

			# Copy the file to target location
			import shutil
			shutil.copy2(source_path, self.google_services_target)
			self.log(f"Copied google-services.json from {source_path}", "SUCCESS")
			self.log(f"FCM will be available for package: {package_name}", "SUCCESS")

			return True

		except Exception as e:
			self.log(f"Error copying google-services.json: {e}", "ERROR")
			return False

	def run(self) -> bool:

		"""Run all configuration steps"""
		self.log("Starting Android generated files patching...", "INFO")

		if not self.check_prerequisites():
			return False

		steps = [
			("Fix AndroidManifest.xml", self.fix_android_manifest),
			("Configure build.gradle.kts", self.configure_build_gradle),
			("Patch colors.xml", self.patch_colors_xml),
			("Fix Kotlin versions", self.fix_kotlin_versions),
			("Copy google-services.json", self.copy_google_services_json),
		]

		success = True
		for step_name, step_func in steps:
			self.log(f"Step: {step_name}", "INFO")
			if not step_func():
				success = False
				self.log(f"Failed: {step_name}", "ERROR")
			else:
				self.log(f"Completed: {step_name}", "SUCCESS")

		if success:
			self.log("Android generated files patching completed successfully!", "SUCCESS")
		else:
			self.log("Android configuration completed with errors", "ERROR")

		return success





def main():
	"""Main entry point"""
	script_path = Path(__file__).parent
	project_root = script_path.parent

	configurer = AndroidConfigurer(project_root)
	success = configurer.run()

	sys.exit(0 if success else 1)


if __name__ == "__main__":
	main()
