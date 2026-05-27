/**
 * auth.js — 全局 JWT 认证拦截器 + 错误边界 + 深色模式。
 *
 * 自动注入到所有 fetch 请求：
 * 1. 自动添加 Authorization: Bearer <token>
 * 2. 401 时尝试 refresh token
 * 3. refresh 失败则跳转登录页
 * 4. 根据 localStorage 自动设置深色模式
 * 5. 统一错误边界：网络超时/服务器错误自动提示
 */

(function () {
    // ── 深色模式 ──────────────────────────────────────────────
    if (localStorage.getItem('theme') === 'dark') {
        document.documentElement.dataset.theme = 'dark';
    }

    const ACCESS_KEY = "pipeline_access_token";
    const REFRESH_KEY = "pipeline_refresh_token";

    function getToken() {
        let token = localStorage.getItem(ACCESS_KEY);
        if (!token) {
            const match = document.cookie.match(/(?:^|;\s*)pipeline_token=([^;]*)/);
            if (match) {
                token = decodeURIComponent(match[1]);
                localStorage.setItem(ACCESS_KEY, token);
            }
        }
        return token;
    }

    async function tryRefresh() {
        const refresh = localStorage.getItem(REFRESH_KEY);
        if (!refresh) return false;
        try {
            const r = await _rawFetch("/api/auth/refresh", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: refresh }),
            });
            if (!r.ok) return false;
            const data = await r.json();
            localStorage.setItem(ACCESS_KEY, data.access_token);
            if (data.refresh_token) {
                localStorage.setItem(REFRESH_KEY, data.refresh_token);
            }
            return true;
        } catch {
            return false;
        }
    }

    function clearAuth() {
        localStorage.removeItem(ACCESS_KEY);
        localStorage.removeItem(REFRESH_KEY);
    }

    // ── 全局错误处理 ──────────────────────────────────────────
    function isApiRequest(url) {
        var u = typeof url === 'string' ? url : (url.url || '');
        return u.indexOf('/api/') !== -1;
    }

    function handleFetchError(url, error) {
        // 网络错误（无连接 / 超时）
        if (error.name === 'AbortError') {
            console.warn('[Pipeline] 请求超时:', url);
            if (isApiRequest(url) && typeof showToast !== 'undefined') {
                showToast('请求超时，请检查网络连接', 'warning');
            }
            return;
        }
        // 离线
        if (!navigator.onLine) {
            console.warn('[Pipeline] 网络离线');
            if (typeof showToast !== 'undefined') {
                showToast('网络已断开，请检查连接', 'error');
            }
            return;
        }
        console.error('[Pipeline] 请求失败:', url, error);
        if (isApiRequest(url) && typeof showToast !== 'undefined') {
            showToast('网络错误，请稍后重试', 'error');
        }
    }

    // 5xx 服务器错误
    function handleServerError(response, url) {
        if (response.status >= 500 && isApiRequest(url) && typeof showToast !== 'undefined') {
            showToast('服务器繁忙，请稍后重试', 'error');
        }
        if (response.status === 403) {
            console.warn('[Pipeline] 权限不足:', url);
            if (typeof showToast !== 'undefined') {
                showToast('权限不足', 'error');
            }
        }
    }

    // 保存原始 fetch（用于 refresh 调用，避免循环）
    const _rawFetch = window.fetch.bind(window);
    const _fetch = window.fetch;

    // 重写 fetch，自动注入 Authorization header + 超时 + 错误边界
    window.fetch = async function (url, options) {
        options = options || {};
        const token = getToken();

        // 自动注入 token（同源 API）
        if (token) {
            options.headers = {
                ...(options.headers || {}),
                Authorization: "Bearer " + token,
            };
        }

        // 无超时则默认 30s
        if (!options.signal) {
            var controller = new AbortController();
            options.signal = controller.signal;
            var timeoutId = setTimeout(function() { controller.abort(); }, 30000);
        }

        var response;
        try {
            response = await _fetch(url, options);
        } catch (error) {
            handleFetchError(url, error);
            throw error;
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
        }

        // 401 自动刷新
        if (response.status === 401 && token) {
            var refreshed = await tryRefresh();
            if (refreshed) {
                options.headers = {
                    ...(options.headers || {}),
                    Authorization: "Bearer " + getToken(),
                };
                // 重新发起请求（不带 signal 因为可能已 abort）
                var retryOpts = Object.assign({}, options);
                delete retryOpts.signal;
                try {
                    response = await _fetch(url, retryOpts);
                } catch (error) {
                    handleFetchError(url, error);
                    throw error;
                }
            } else {
                clearAuth();
                window.location.href = "/login";
                return response;
            }
        }

        // 5xx / 403 错误处理
        handleServerError(response, url);

        return response;
    };
})();
