#!/usr/bin/env fish

# Build release APK
source (dirname (status --current-filename))/../env/android-release.env

# Check if gen directory exists, if not, run release-init.sh
if not test -d src-tauri/gen
    echo "📁 gen directory not found, running release-init.sh..."
    ./scripts/android/release-init.sh
    if test $status -ne 0
        echo "❌ release-init.sh failed. Exiting."
        exit 1
    end
    echo "✅ release-init.sh completed successfully"
end

cp -r src-tauri/icons/android/* src-tauri/gen/android/app/src/main/res/;

echo "🔨 Building release APK..."
echo "📱 VITE_DEV_MODE: $VITE_DEV_MODE"
echo "🌐 VITE_BACKEND_ANDROID: $VITE_BACKEND_ANDROID"

set -q FORMAT; or set -gx FORMAT "--apk" # apk or aab

bun run tauri android build $FORMAT #true

if test $status -eq 0
	if test "$FORMAT" = "aab"
		echo "✅ Release AAB build successful!"
		echo "📦 AAB locations:"
		find src-tauri/gen/android/app/build/outputs/bundle -name "*.aab" -type f | while read aab
			echo "  📱 "(basename $aab)": "(du -h $aab | cut -f1)
		end
	else if test "$FORMAT" = "apk"
		echo "✅ Release APK build successful!"
		echo "📦 APK locations:"
		find src-tauri/gen/android/app/build/outputs/apk -name "*.apk" -type f | while read apk
			echo "  📱 "(basename $apk)": "(du -h $apk | cut -f1)
		end
	end
else
    echo "❌ Release APK build failed. Check the error messages above."
    exit 1
end
