import { fetchSession, login } from "/services/api.js";

const elements = {
  form: document.getElementById("login-form"),
  email: document.getElementById("login-email"),
  password: document.getElementById("login-password"),
  loginButton: document.getElementById("login-button"),
  loginStatus: document.getElementById("login-status"),
  toast: document.getElementById("toast"),
};

function readNextPath() {
  const query = new URLSearchParams(window.location.search);
  const nextPath = query.get("next")?.trim() || "";
  if (!nextPath.startsWith("/")) {
    return "/pages/index.html";
  }
  return nextPath;
}

function showToast(message, type = "info") {
  elements.toast.textContent = message;
  elements.toast.className = `toast ${type}`;
  window.clearTimeout(showToast.timerId);
  showToast.timerId = window.setTimeout(() => {
    elements.toast.className = "toast hidden";
  }, 2800);
}

function setSubmitting(isSubmitting) {
  document.body.classList.toggle("loading", isSubmitting);
  elements.loginButton.disabled = isSubmitting;
  elements.loginButton.textContent = isSubmitting ? "正在登录..." : "登录并进入项目管理";
}

function setStatus(text, type = "info") {
  elements.loginStatus.textContent = text;
  elements.loginStatus.className = `auth-status ${type}`;
}

async function ensureAnonymousOnly() {
  try {
    const payload = await fetchSession();
    if (payload?.user) {
      window.location.replace(readNextPath());
    }
  } catch (error) {
    if (error.status === 401) {
      return;
    }
    throw error;
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const email = elements.email.value.trim();
  const password = elements.password.value;
  if (!email || !password) {
    setStatus("请先输入邮箱和密码。", "error");
    return;
  }

  setSubmitting(true);
  setStatus("正在校验账号...", "info");
  try {
    const payload = await login(email, password);
    setStatus(`登录成功：${payload.user?.email || email}`, "success");
    showToast("登录成功，正在进入项目管理页。", "success");
    window.setTimeout(() => {
      window.location.assign(readNextPath());
    }, 200);
  } catch (error) {
    setStatus(error.message, "error");
    showToast(error.message, "error");
  } finally {
    setSubmitting(false);
  }
}

function bindEvents() {
  elements.form.addEventListener("submit", (event) => {
    void handleLogin(event);
  });
}

async function main() {
  bindEvents();
  try {
    await ensureAnonymousOnly();
  } catch (error) {
    setStatus(error.message, "error");
  }
}

void main();
