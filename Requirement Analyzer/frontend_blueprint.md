# Frontend Blueprint & Security Guide - AI Requirement Analyzer

This guide details how to build a modern, high-fidelity frontend dashboard for the AI Requirement Analyzer, secure the client session using JWT, and render analysis data.

---

## 1. JWT Storage & Session Management

To keep users logged in and securely access protected API routes, the frontend must store the JWT access token and include it in every API request.

### LocalStorage vs. HttpOnly Cookie
- **LocalStorage (Recommended for SPA Prototyping)**: Easier to implement, accessible via JavaScript. Perfect for university project defense.
- **HttpOnly Cookie (Production Standard)**: Mitigates XSS vulnerabilities by preventing JS access.

### Client-Side Session Workflow (LocalStorage)

#### A. Storing the Token upon Login
When a user logs in successfully via `/api/auth/login`, the backend returns a JSON payload containing the access token. Store this token in `localStorage`:

```javascript
// Example JavaScript Login Handler
async function handleLogin(username, password) {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  const response = await fetch('http://localhost:8000/api/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: formData
  });

  if (response.ok) {
    const data = await response.json();
    // Save JWT token in localStorage
    localStorage.setItem('access_token', data.access_token);
    window.location.href = '/dashboard.html';
  } else {
    alert('Authentication failed');
  }
}
```

#### B. Authenticating API Requests
For every subsequent request to protected routes (like `/api/analyze/text` or `/api/dashboard/metrics`), retrieve the token and include it in the `Authorization` header as a Bearer token:

```javascript
async function fetchDashboardMetrics() {
  const token = localStorage.getItem('access_token');
  if (!token) {
    // Redirect to login if token is missing
    window.location.href = '/login.html';
    return;
  }

  const response = await fetch('http://localhost:8000/api/dashboard/metrics', {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (response.status === 401) {
    // Token expired or invalid
    localStorage.removeItem('access_token');
    window.location.href = '/login.html';
    return;
  }

  return await response.json();
}
```

#### C. Logout
Simply clear the token from localStorage and redirect the user back to the login screen:
```javascript
function handleLogout() {
  localStorage.removeItem('access_token');
  window.location.href = '/login.html';
}
```

---

## 2. Interactive Dashboard Layout (HTML5 + TailwindCSS)

The following TailwindCSS mock structure presents a premium dark-mode dashboard tailored for displaying analysis results, complete with metric cards, interactive staging, tabular data grids with priority badges, and side-by-side rewrite suggestions.

```html
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Requirement Analyzer - Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Outfit', sans-serif; }
  </style>
</head>
<body class="bg-[#0f172a] text-slate-100 min-h-screen">

  <!-- Navigation Bar -->
  <nav class="border-b border-slate-800 bg-[#0f172a]/80 backdrop-blur-md sticky top-0 z-50 px-6 py-4 flex justify-between items-center">
    <div class="flex items-center space-x-3">
      <div class="h-9 w-9 rounded-lg bg-gradient-to-tr from-indigo-500 to-violet-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/20">AR</div>
      <span class="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">AI Requirement Analyzer</span>
    </div>
    <div class="flex items-center space-x-6">
      <span class="text-sm text-slate-400">Welcome, <strong class="text-indigo-400" id="username-display">User</strong></span>
      <button onclick="handleLogout()" class="text-sm px-4 py-2 rounded-lg border border-slate-700 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400 transition">Logout</button>
    </div>
  </nav>

  <main class="max-w-7xl mx-auto px-6 py-8 space-y-8">
    
    <!-- Row 1: Metrics Overview Cards -->
    <section class="grid grid-cols-1 md:grid-cols-4 gap-6">
      <!-- Total Card -->
      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-indigo-500/10 rounded-full blur-xl group-hover:bg-indigo-500/20 transition-all duration-300"></div>
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Requirements</p>
        <p class="text-4xl font-bold mt-2" id="metric-total">0</p>
      </div>

      <!-- Category Split -->
      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-emerald-500/10 rounded-full blur-xl group-hover:bg-emerald-500/20 transition-all duration-300"></div>
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Functional vs NFR</p>
        <p class="text-4xl font-bold mt-2"><span id="metric-fr" class="text-emerald-400">0</span> <span class="text-slate-600 text-2xl">/</span> <span id="metric-nfr" class="text-blue-400">0</span></p>
      </div>

      <!-- Completeness Score -->
      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-amber-500/10 rounded-full blur-xl group-hover:bg-amber-500/20 transition-all duration-300"></div>
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Avg Completeness</p>
        <p class="text-4xl font-bold mt-2" id="metric-completeness">0%</p>
      </div>

      <!-- Aggregated Risk Score -->
      <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-red-500/10 rounded-full blur-xl group-hover:bg-red-500/20 transition-all duration-300"></div>
        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Aggregated System Risk</p>
        <p class="text-4xl font-bold mt-2 text-rose-500" id="metric-risk">0.0</p>
      </div>
    </section>

    <!-- Row 2: Input Staging View -->
    <section class="bg-slate-900/40 border border-slate-800 rounded-3xl p-8 shadow-2xl relative overflow-hidden">
      <div class="absolute inset-0 bg-gradient-to-tr from-indigo-500/5 via-transparent to-transparent"></div>
      <h2 class="text-2xl font-bold mb-4 relative z-10">Requirement Input Stage</h2>
      <p class="text-slate-400 text-sm mb-6 relative z-10">Enter bulk requirement statements (one per sentence or paragraph) below to run analysis. Check "Persist to Dashboard" to save the results permanently.</p>
      
      <div class="space-y-4 relative z-10">
        <textarea id="requirement-input" rows="6" placeholder="Example: The system shall encrypt user passwords securely. The report module should generate reports quickly for users..." class="w-full bg-slate-950/80 border border-slate-800 rounded-2xl px-5 py-4 text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition duration-200 resize-none font-light"></textarea>
        
        <div class="flex items-center justify-between">
          <label class="flex items-center space-x-3 cursor-pointer">
            <input type="checkbox" id="persist-checkbox" class="h-4 w-4 rounded border-slate-800 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-900 bg-slate-950">
            <span class="text-sm text-slate-300">Persist to History & Dashboard Metrics</span>
          </label>
          <button onclick="triggerAnalysis()" class="px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 font-medium tracking-wide shadow-lg shadow-indigo-500/20 hover:shadow-indigo-600/30 transform active:scale-95 transition">Analyze Requirements</button>
        </div>
      </div>
    </section>

    <!-- Row 3: Tabular Grid View -->
    <section class="bg-slate-900/40 border border-slate-800 rounded-3xl p-8 shadow-2xl">
      <h2 class="text-2xl font-bold mb-6">Detailed Quality Breakdown</h2>
      
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-800">
          <thead>
            <tr>
              <th class="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Requirement Statement</th>
              <th class="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Category</th>
              <th class="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Completeness</th>
              <th class="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Priority</th>
              <th class="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Actions</th>
            </tr>
          </thead>
          <tbody id="requirements-table-body" class="divide-y divide-slate-800/60 bg-transparent">
            <!-- Dynamic rows will be inserted here -->
            <tr>
              <td colspan="5" class="px-6 py-8 text-center text-slate-500 text-sm">No analysis performed yet. Input text above.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Row 4: Conflict Alerts -->
    <section id="conflict-section" class="hidden bg-rose-500/10 border border-rose-500/20 rounded-3xl p-8">
      <div class="flex items-center space-x-3 text-rose-400 mb-4">
        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
        <h2 class="text-xl font-bold">Detected Logic Conflicts</h2>
      </div>
      <div class="space-y-3" id="conflicts-container">
        <!-- Dynamic conflicts here -->
      </div>
    </section>

    <!-- Row 5: Suggestion Cards (Interactive Side-by-Side) -->
    <section class="grid grid-cols-1 md:grid-cols-2 gap-8" id="suggestion-cards-section">
      <!-- Dynamic side-by-side suggestions inserted here -->
    </section>

  </main>
</body>
</html>
```

---

## 3. UI Component Badges Reference

To provide an intuitive dashboard layout, render dynamic badges depending on the completeness percentage and category outputs:

### Completeness Badge Color Logic
- **Red Badge (`0% - 25%`)**: Critical issues, components missing.
  `bg-rose-500/10 text-rose-400 border-rose-500/20`
- **Amber Badge (`50% - 75%`)**: Partially complete.
  `bg-amber-500/10 text-amber-400 border-amber-500/20`
- **Green Badge (`100%`)**: Fully complete (Actor, Action, Condition, Expected Outcome detected).
  `bg-emerald-500/10 text-emerald-400 border-emerald-500/20`

### Category Badge Color Logic
- **Functional (FR)**: `bg-teal-500/10 text-teal-400 border-teal-500/20`
- **Non-Functional (NFR)**: `bg-indigo-500/10 text-indigo-400 border-indigo-500/20`

### Priority Badge Color Logic
- **Must Have**: `bg-red-500/10 text-red-400 border-red-500/20`
- **Should Have**: `bg-yellow-500/10 text-yellow-400 border-yellow-500/20`
- **Could Have**: `bg-blue-500/10 text-blue-400 border-blue-500/20`
- **Won't Have**: `bg-gray-500/10 text-gray-400 border-gray-500/20`
