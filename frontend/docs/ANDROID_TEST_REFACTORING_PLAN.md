# Android Test Refactoring Plan

## 🎯 **Current Problems**

### ❌ **Massive Duplication Found:**
- **98 screenshot calls** - no standardization
- **46 hamburger menu interactions** - identical code repeated
- **WebView context switching** - same pattern everywhere
- **Login flows** - identical auth logic duplicated
- **Camera workflows** - repeated patterns

### ❌ **Poor Organization:**
- **12 overlapping test files** with similar purposes
- **No page object models** - raw selectors everywhere
- **No reusable workflows** - copy-pasted test logic

## 🏗️ **Refactoring Solution**

### ✅ **Page Objects Created:**

**1. `HillviewApp.page.ts`** - Main app interactions
- Hamburger menu actions
- Camera button clicks
- Screenshot standardization
- Error detection
- App readiness checks

**2. `WebViewAuth.page.ts`** - Authentication flows
- WebView context switching
- Login workflow
- Sources navigation
- Mapillary toggle
- Auth state detection

**3. `CameraFlow.page.ts`** - Photo capture workflow
- Permission handling
- Photo capture steps
- Photo confirmation
- Return to main app
- Complete camera workflow

**4. `TestWorkflows.ts`** - High-level user journeys
- Complete login workflow
- Complete photo capture workflow
- Auth + photo workflow
- Source configuration
- Health checks

## 📋 **File Consolidation Plan**

### 🔄 **Files to Merge:**

**Authentication Tests:**
- ❌ `android-login.test.ts` (basic login)
- ❌ `android-auth-workflow.test.ts` (OAuth + persistence)
- ✅ **→ `android-auth.test.ts`** (consolidated auth tests)

**Camera Tests:**
- ❌ `android-camera.test.ts` (basic camera)
- ❌ Parts of `android-photo-simple.test.ts` (camera workflow)
- ✅ **→ `android-camera.refactored.test.ts`** (consolidated camera tests)

**Complete Workflows:**
- ❌ `android-complete-workflow.test.ts`
- ❌ `android-workflow.test.ts`  
- ❌ `android-photo-upload-workflow.test.ts`
- ✅ **→ `android-e2e-workflows.test.ts`** (end-to-end tests)

**Upload Tests:**
- ❌ `android-upload.test.ts` (upload verification)
- ❌ Upload parts from other tests
- ✅ **→ `android-upload.refactored.test.ts`** (consolidated upload tests)

**Diagnostic Tests:**
- ❌ `android-ui-diagnostic.test.ts`
- ❌ `android-ui-exploration.test.ts`
- ❌ `android-quick-test.test.ts`
- ✅ **→ `android-diagnostics.test.ts`** (debugging and exploration)

**Health Tests:**
- ✅ `android-health-check.test.ts` (keep as-is - already focused)

## 🚀 **Implementation Steps**

### **Phase 1: Core Infrastructure ✅**
- ✅ Created page objects
- ✅ Created workflow helpers
- ✅ Demonstrated refactored tests

### **Phase 2: File Consolidation**
1. **Create consolidated test files** using page objects
2. **Migrate existing test logic** to new structure
3. **Update package.json scripts** to reference new files
4. **Archive old test files** (move to `test/legacy/`)

### **Phase 3: Optimization**
1. **Add more page object methods** as needed
2. **Create shared test data** (credentials, test constants)
3. **Improve error handling** across all tests
4. **Add test utilities** for common operations

## 📊 **Benefits of Refactoring**

### **Before Refactoring:**
- 🐌 **98 duplicate screenshot calls**
- 🐌 **46 duplicate menu interactions** 
- 🔄 **Copy-paste everywhere**
- 🐛 **Hard to maintain when UI changes**
- 📁 **12 confusing test files**

### **After Refactoring:**
- ⚡ **Standardized screenshot helper**
- ⚡ **Reusable menu interaction**
- 🎯 **Single source of truth for UI actions**
- 🛠️ **Easy to update when UI changes**
- 📁 **5-6 focused test files**

## 🔧 **Example: Before vs After**

### ❌ **Before (Duplicated everywhere):**
```typescript
// In 10+ test files:
const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
await hamburgerMenu.waitForDisplayed({ timeout: 10000 });
await hamburgerMenu.click();
await driver.pause(2000);

const contexts = await driver.getContexts();
const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
if (webViewContexts.length > 0) {
    await driver.switchContext(webViewContexts[0]);
    // ... login logic ...
}
```

### ✅ **After (Reusable):**
```typescript
// In any test file:
const workflows = new TestWorkflows();
const success = await workflows.performCompleteLogin();
expect(success).toBe(true);
```

## 📈 **Estimated Improvements**

### **Code Reduction:**
- **~70% reduction** in test code duplication
- **~50% fewer lines** of test code overall
- **~80% reduction** in UI selector maintenance

### **Maintenance:**
- **1 place to update** when UI changes (page objects)
- **Consistent error handling** across all tests
- **Standardized screenshots** and logging

### **Test Quality:**
- **More reliable** due to consistent patterns
- **Easier to debug** with standardized workflows
- **Better test isolation** with clean helper methods

## 🎯 **Next Steps**

1. **Review the refactored examples** (`android-auth.test.ts`, `android-camera.refactored.test.ts`)
2. **Choose consolidation approach:**
   - Gradual migration (update tests one by one)
   - Complete rewrite (create all new consolidated files)
3. **Update CI/CD scripts** to use new test files
4. **Archive legacy tests** once migration is complete

The refactoring will make the test suite much more maintainable and reliable! 🎉