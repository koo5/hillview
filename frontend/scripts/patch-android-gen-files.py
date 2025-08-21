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
        self.gitignore_file = project_root / ".gitignore"
        
        # External keystore configuration (maintained by user)
        self.keystore_props_path = Path.home() / "secrets" / "keystore.properties"
    
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
            
            # Write back only if changes were made
            if changes_made:
                # Write with proper formatting
                with open(self.manifest_file, 'w', encoding='utf-8') as f:
                    dom.writexml(f, encoding='utf-8', addindent='    ', newl='\n')
                self.log("AndroidManifest.xml updated successfully", "SUCCESS")
            else:
                self.log("AndroidManifest.xml already correctly configured", "SUCCESS")
            
            return True
            
        except Exception as e:
            self.log(f"Error fixing AndroidManifest.xml: {e}", "ERROR")
            return False
    
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
    
    def update_gitignore(self) -> bool:
        """Add Android signing files to .gitignore (defensive measure)"""
        self.log("Updating .gitignore...")
        
        try:
            # Read existing .gitignore or create empty
            if self.gitignore_file.exists():
                content = self.gitignore_file.read_text()
            else:
                content = ""
                self.log("Creating .gitignore file", "INFO")
            
            # Check if Android signing entries exist (defensive)
            android_entries = [
                "*.jks",
                "*.keystore",
                "keystore.properties"
            ]
            
            entries_to_add = []
            for entry in android_entries:
                if entry not in content:
                    entries_to_add.append(entry)
            
            if entries_to_add:
                # Add Android signing section
                if content and not content.endswith('\n'):
                    content += '\n'
                
                content += '\n# Android signing (defensive - files should be external anyway)\n'
                for entry in entries_to_add:
                    content += f"{entry}\n"
                
                self.gitignore_file.write_text(content)
                self.log("Added Android signing files to .gitignore", "SUCCESS")
            else:
                self.log(".gitignore already configured", "SUCCESS")
            
            return True
            
        except Exception as e:
            self.log(f"Error updating .gitignore: {e}", "ERROR")
            return False
    
    def run(self) -> bool:
        """Run all configuration steps"""
        self.log("Starting Android generated files patching...", "INFO")
        
        if not self.check_prerequisites():
            return False
        
        steps = [
            ("Fix AndroidManifest.xml", self.fix_android_manifest),
            ("Configure build.gradle.kts", self.configure_build_gradle),
            ("Update .gitignore", self.update_gitignore)
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
            self._show_next_steps()
        else:
            self.log("Android configuration completed with errors", "ERROR")
        
        return success
    
    def _show_next_steps(self):
        """Show next steps to user"""
        self.log("\nNext steps:", "INFO")
        
        if not self.keystore_props_path.exists():
            self.log(f"1. Create {self.keystore_props_path} with:", "WARNING")
            self.log("   password=your-password", "INFO")
            self.log("   keyAlias=your-alias", "INFO")
            self.log("   storeFile=/path/to/your/keystore.jks", "INFO")
        else:
            self.log(f"1. ✓ External keystore.properties found", "SUCCESS")
        
        self.log("2. Test build: ./scripts/tauri-android.sh android build --apk", "INFO")
        
        self.log(f"\nConfiguration references: {self.keystore_props_path}", "INFO")
        self.log("All sensitive files are kept outside the repository", "SUCCESS")


def main():
    """Main entry point"""
    script_path = Path(__file__).parent
    project_root = script_path.parent
    
    configurer = AndroidConfigurer(project_root)
    success = configurer.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()