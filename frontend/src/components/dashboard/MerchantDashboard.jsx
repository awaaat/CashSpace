import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import api from "../../api/axios";
import styles from "./MerchantDashboard.module.css";

// ── Internal API client (keeps component self-contained) ─────────────────────
const merchantApi = {
  getMe:            ()          => api.get("/merchants/me/"),
  register:         (data)      => api.post("/merchants/register/", data),
  update:           (data)      => api.patch("/merchants/me/", data),
  getAnalytics:     (period)    => api.get("/merchants/me/analytics/", { params: { period } }),
  getKeys:          ()          => api.get("/merchants/me/keys/"),
  rotateKey:        (env)       => api.post("/merchants/me/keys/rotate/", { env }),
  toggleMode:       (mode)      => api.post("/merchants/me/keys/toggle-mode/", { mode }),
  getSales:         (params)    => api.get("/merchants/me/sales/", { params }),
  getSale:          (id)        => api.get(`/merchants/me/sales/${id}/`),
  retrigger:        (id)        => api.post(`/merchants/me/sales/${id}/retrigger/`),
  getProducts:      ()          => api.get("/merchants/me/products/"),
  createProduct:    (data)      => api.post("/merchants/me/products/", data),
  updateProduct:    (id, data)  => api.patch(`/merchants/me/products/${id}/`, data),
  deleteProduct:    (id)        => api.delete(`/merchants/me/products/${id}/`),
  testSale:         (pid)       => api.post(`/merchants/me/products/${pid}/test-sale/`),
  getActions:       (pid)       => api.get(`/merchants/me/products/${pid}/actions/`),
  createAction:     (pid, d)    => api.post(`/merchants/me/products/${pid}/actions/`, d),
  updateAction:     (pid, id, d)=> api.patch(`/merchants/me/products/${pid}/actions/${id}/`, d),
  deleteAction:     (pid, id)   => api.delete(`/merchants/me/products/${pid}/actions/${id}/`),
  getWebhookLogs:   (params)    => api.get("/merchants/me/webhook-logs/", { params }),
  retryWebhook:     (id)        => api.post(`/merchants/me/webhook-logs/${id}/retry/`),
};

// ── Utilities ─────────────────────────────────────────────────────────────────
const fmt  = (n) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n ?? 0);
const date = (iso) => iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";
const copyToClipboard = async (text) => { try { await navigator.clipboard.writeText(text); return true; } catch { return false; } };

const NAV = [
  { id: "overview",     label: "Overview"    },
  { id: "products",     label: "Products"    },
  { id: "sales",        label: "Sales CRM"   },
  { id: "automations",  label: "Automations" },
  { id: "webhooks",     label: "Webhook Logs"},
  { id: "settings",     label: "Settings"    },
];

// ── Shared UI primitives ──────────────────────────────────────────────────────
function Field({ label, children, hint }) {
  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel}>{label}</label>
      {children}
      {hint && <span className={styles.fieldHint}>{hint}</span>}
    </div>
  );
}

function Panel({ title, action, children }) {
  return (
    <div className={styles.panel}>
      {(title || action) && (
        <div className={styles.panelHeader}>
          {title && <h3 className={styles.panelTitle}>{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

function StatusBadge({ status }) {
  const cls = status?.toLowerCase().replace(/_/g, "-");
  return <span className={`${styles.statusBadge} ${styles[cls] || ""}`}>{status?.replace(/_/g, " ")}</span>;
}

function ModeBadge({ isTest }) {
  return isTest
    ? <span className={styles.testModeBadge}>TEST</span>
    : <span className={styles.liveModeBadge}>LIVE</span>;
}

function Toast({ msg, type, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 4000); return () => clearTimeout(t); }, [onClose]);
  const typeClass = type === "success" ? styles.toastSuccess : type === "error" ? styles.toastError : styles.toastInfo;
  return (
    <div className={`${styles.toast} ${typeClass}`}>
      <span className={styles.toastMsg}>{msg}</span>
      <button onClick={onClose} className={styles.toastClose}>×</button>
    </div>
  );
}

function CopyButton({ text, showToast }) {
  const [copied, setCopied] = useState(false);
  const handle = async (e) => {
    e.stopPropagation();
    const ok = await copyToClipboard(text);
    if (ok) { setCopied(true); setTimeout(() => setCopied(false), 2000); showToast("Copied!", "success"); }
    else showToast("Copy failed", "error");
  };
  return (
    <button className={styles.copyBtn} onClick={handle}>
      {copied ? "Copied ✓" : "Copy link"}
    </button>
  );
}

// ── Mini sparkline chart (pure SVG, no library) ───────────────────────────────
function SparkChart({ data = [], color = "#f0c040" }) {
  if (!data.length) return <div className={styles.chartEmpty}>No data for this period</div>;
  const vals = data.map(d => parseFloat(d.revenue) || 0);
  const max   = Math.max(...vals, 1);
  const W = 500, H = 80, pad = 4;
  const points = vals.map((v, i) => {
    const x = pad + (i / Math.max(vals.length - 1, 1)) * (W - pad * 2);
    const y = H - pad - ((v / max) * (H - pad * 2));
    return `${x},${y}`;
  }).join(" ");
  const areaPoints = `${pad},${H - pad} ${points} ${W - pad},${H - pad}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={styles.sparkChart} preserveAspectRatio="none">
      <defs>
        <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill="url(#sparkGrad)" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ── Register screen ───────────────────────────────────────────────────────────
function RegisterScreen({ onDone, showToast }) {
  const [form, setForm] = useState({
    business_name: "", description: "", logo_url: "",
    settlement_blockchain: "TRX", settlement_currency: "USDT",
    settlement_wallet_address: "", webhook_url: "", webhook_secret: "",
  });
  const [loading, setLoading] = useState(false);
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault(); setLoading(true);
    try {
      const { data } = await merchantApi.register(form);
      showToast("Merchant account created!", "success");
      onDone(data);
    } catch (err) {
      showToast(err.response?.data?.detail || Object.values(err.response?.data || {})[0]?.[0] || "Registration failed", "error");
    } finally { setLoading(false); }
  };

  return (
    <div className={styles.registerScreen}>
      <div className={styles.registerCard}>
        <div className={styles.registerLogo}>C</div>
        <h2 className={styles.registerTitle}>Become a CashSpace Merchant</h2>
        <p className={styles.registerSub}>Accept payments from your audience worldwide</p>
        <form onSubmit={handleSubmit} className={styles.registerForm}>
          <Field label="Business name *"><input className={styles.input} value={form.business_name} onChange={set("business_name")} placeholder="e.g., Forex Academy Pro" required /></Field>
          <Field label="Description"><textarea className={styles.textarea} value={form.description} onChange={set("description")} placeholder="Short description shown on your checkout pages" /></Field>
          <Field label="Logo URL (optional)"><input className={styles.input} value={form.logo_url} onChange={set("logo_url")} placeholder="https://..." /></Field>
          <div className={styles.rowTwo}>
            <Field label="Settlement blockchain">
              <select className={styles.select} value={form.settlement_blockchain} onChange={set("settlement_blockchain")}>
                <option value="TRX">Tron (TRX)</option><option value="ETH">Ethereum (ETH)</option>
                <option value="BTC">Bitcoin (BTC)</option><option value="BASE">Base</option><option value="POL">Polygon</option>
              </select>
            </Field>
            <Field label="Settlement currency">
              <select className={styles.select} value={form.settlement_currency} onChange={set("settlement_currency")}>
                <option value="USDT">USDT</option><option value="USDC">USDC</option>
                <option value="BTC">BTC</option><option value="ETH">ETH</option><option value="TRX">TRX</option>
              </select>
            </Field>
          </div>
          <Field label="Settlement wallet address" hint="Where your payouts land after CashSpace takes its fee">
            <input className={styles.input} value={form.settlement_wallet_address} onChange={set("settlement_wallet_address")} placeholder="Your wallet address" />
          </Field>
          <button type="submit" className={styles.registerBtn} disabled={loading}>
            {loading ? "Creating…" : "Create merchant account"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Product form ──────────────────────────────────────────────────────────────
function ProductForm({ product, onSave, onCancel, showToast }) {
  const isEdit = !!product?.id;
  const [form, setForm] = useState({
    name:                 product?.name || "",
    description:          product?.description || "",
    product_type:         product?.product_type || "one_time",
    price_usd:            product?.price_usd || "",
    min_price_usd:        product?.min_price_usd || "10",
    collect_telegram:     product?.collect_telegram || false,
    collect_discord:      product?.collect_discord || false,
    collect_phone:        product?.collect_phone || false,
    collect_custom_field: product?.collect_custom_field || "",
    success_redirect_url: product?.success_redirect_url || "",
    max_purchases:        product?.max_purchases || "",
    is_active:            product?.is_active !== false,
  });
  const [loading, setLoading] = useState(false);
  const set  = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));
  const setB = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.checked }));

  const handleSubmit = async (e) => {
    e.preventDefault(); setLoading(true);
    const payload = {
      ...form,
      price_usd:     form.product_type !== "donation" ? parseFloat(form.price_usd) : null,
      min_price_usd: parseFloat(form.min_price_usd) || 10,
      max_purchases: form.max_purchases ? parseInt(form.max_purchases) : null,
    };
    try {
      const { data } = isEdit
        ? await merchantApi.updateProduct(product.id, payload)
        : await merchantApi.createProduct(payload);
      showToast(isEdit ? "Product updated" : "Product created", "success");
      onSave(data);
    } catch (err) {
      showToast(err.response?.data?.detail || Object.values(err.response?.data || {})[0]?.[0] || "Save failed", "error");
    } finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className={styles.productForm}>
      <Field label="Product name *"><input className={styles.input} value={form.name} onChange={set("name")} required placeholder="e.g., VIP Signals Monthly" /></Field>
      <Field label="Description"><textarea className={styles.textarea} value={form.description} onChange={set("description")} placeholder="What does the buyer get?" /></Field>
      <div className={styles.rowTwo}>
        <Field label="Type">
          <select className={styles.select} value={form.product_type} onChange={set("product_type")}>
            <option value="one_time">One-time purchase</option>
            <option value="subscription">Subscription</option>
            <option value="donation">Donation / Pay what you want</option>
          </select>
        </Field>
        {form.product_type !== "donation"
          ? <Field label="Price (USD) *"><input className={styles.input} type="number" min="10" step="0.01" value={form.price_usd} onChange={set("price_usd")} required placeholder="99.00" /></Field>
          : <Field label="Minimum price (USD)"><input className={styles.input} type="number" min="1" step="0.01" value={form.min_price_usd} onChange={set("min_price_usd")} placeholder="10" /></Field>}
      </div>
      <div className={styles.collectBox}>
        <div className={styles.collectTitle}>Collect from buyer</div>
        {[{ k: "collect_telegram", label: "Telegram username" }, { k: "collect_discord", label: "Discord username" }, { k: "collect_phone", label: "Phone number" }].map(({ k, label }) => (
          <label key={k} className={styles.checkboxLabel}>
            <input type="checkbox" checked={form[k]} onChange={setB(k)} className={styles.checkbox} />{label}
          </label>
        ))}
        <Field label="Custom field label (optional)" hint="e.g., 'Trading account number'">
          <input className={styles.input} value={form.collect_custom_field} onChange={set("collect_custom_field")} placeholder="Leave blank to disable" />
        </Field>
      </div>
      <Field label="Success redirect URL (optional)"><input className={styles.input} value={form.success_redirect_url} onChange={set("success_redirect_url")} placeholder="https://your-site.com/thank-you" /></Field>
      <Field label="Max purchases (optional)" hint="Leave blank for unlimited"><input className={styles.input} type="number" min="1" value={form.max_purchases} onChange={set("max_purchases")} placeholder="Unlimited" /></Field>
      <label className={styles.checkboxLabel}>
        <input type="checkbox" checked={form.is_active} onChange={setB("is_active")} className={styles.checkbox} />Product is active (accepting payments)
      </label>
      <div className={styles.formActions}>
        <button type="button" className={styles.cancelBtn} onClick={onCancel}>Cancel</button>
        <button type="submit" className={styles.submitBtn} disabled={loading}>{loading ? "Saving…" : isEdit ? "Save changes" : "Create product"}</button>
      </div>
    </form>
  );
}

// ── Action form ───────────────────────────────────────────────────────────────
function ActionForm({ action, productId, onSave, onCancel, showToast }) {
  const isEdit = !!action?.id;
  const [type, setType]         = useState(action?.action_type || "telegram_invite");
  const [priority, setPriority] = useState(action?.priority ?? 0);
  const [isActive, setIsActive] = useState(action?.is_active !== false);
  const [config, setConfig]     = useState(action?.config || { invite_link: "" });
  const [loading, setLoading]   = useState(false);
  const setConf = (k) => (e) => setConfig(c => ({ ...c, [k]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault(); setLoading(true);
    const payload = { action_type: type, priority: parseInt(priority), is_active: isActive, config };
    try {
      const { data } = isEdit
        ? await merchantApi.updateAction(productId, action.id, payload)
        : await merchantApi.createAction(productId, payload);
      showToast(isEdit ? "Action updated" : "Action added", "success");
      onSave(data);
    } catch (err) {
      showToast(err.response?.data?.config?.[0] || err.response?.data?.detail || "Save failed", "error");
    } finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className={styles.actionForm}>
      <div className={styles.rowTwo}>
        <Field label="Action type">
          <select className={styles.select} value={type} onChange={e => setType(e.target.value)} disabled={isEdit}>
            <option value="telegram_invite">Telegram group invite</option>
            <option value="email_delivery">Email delivery</option>
            <option value="webhook">Webhook to your server</option>
            <option value="discord_role">Discord role grant</option>
          </select>
        </Field>
        <Field label="Priority" hint="Lower = runs first"><input className={styles.input} type="number" min="0" value={priority} onChange={e => setPriority(e.target.value)} /></Field>
      </div>
      {type === "telegram_invite" && <Field label="Invite link *" hint="e.g. https://t.me/+abc123"><input className={styles.input} value={config.invite_link || ""} onChange={setConf("invite_link")} placeholder="https://t.me/+..." required /></Field>}
      {type === "email_delivery" && (<>
        <Field label="Email subject *"><input className={styles.input} value={config.subject || ""} onChange={setConf("subject")} placeholder="Your access to {product_name} is ready" required /></Field>
        <Field label="Body template *" hint="Placeholders: {buyer_name} {buyer_email} {product_name} {merchant_name} {amount_usd} {download_link}">
          <textarea className={styles.textarea} value={config.body_template || ""} onChange={setConf("body_template")} required placeholder={"Hi {buyer_name},\n\nHere is your access:\n{download_link}\n\n— {merchant_name}"} />
        </Field>
        <Field label="Download link (optional)"><input className={styles.input} value={config.download_link || ""} onChange={setConf("download_link")} placeholder="https://..." /></Field>
        <Field label="From name (optional)"><input className={styles.input} value={config.from_name || ""} onChange={setConf("from_name")} placeholder="Defaults to your business name" /></Field>
      </>)}
      {type === "webhook" && (<>
        <Field label="Webhook URL *"><input className={styles.input} value={config.url || ""} onChange={setConf("url")} placeholder="https://your-server.com/webhook" required /></Field>
        <Field label="Secret (optional)" hint="Sent as X-CashSpace-Signature header (HMAC-SHA256)"><input className={styles.input} value={config.secret || ""} onChange={setConf("secret")} placeholder="Optional signing secret" /></Field>
      </>)}
      {type === "discord_role" && (<>
        <Field label="Guild ID *"><input className={styles.input} value={config.guild_id || ""} onChange={setConf("guild_id")} required /></Field>
        <Field label="Role ID *"><input className={styles.input} value={config.role_id || ""} onChange={setConf("role_id")} required /></Field>
        <Field label="Bot token *"><input className={styles.input} value={config.bot_token || ""} onChange={setConf("bot_token")} required type="password" /></Field>
      </>)}
      <label className={styles.checkboxLabel}>
        <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} className={styles.checkbox} />Action is active
      </label>
      <div className={styles.formActions}>
        <button type="button" className={styles.cancelBtn} onClick={onCancel}>Cancel</button>
        <button type="submit" className={styles.submitBtn} disabled={loading}>{loading ? "Saving…" : isEdit ? "Save changes" : "Add action"}</button>
      </div>
    </form>
  );
}

// ── API Keys panel ────────────────────────────────────────────────────────────
function APIKeysPanel({ merchant, showToast, onModeChange }) {
  const [keys, setKeys]               = useState(null);
  const [loading, setLoading]         = useState(true);
  const [rotating, setRotating]       = useState(null);   // "test" | "live" | null
  const [toggling, setToggling]       = useState(false);
  const [newKey, setNewKey]           = useState(null);   // { env, key } shown once
  const [confirmRotate, setConfirmRotate] = useState(null); // "test" | "live"

  useEffect(() => { loadKeys(); }, []);

  const loadKeys = async () => {
    try { const { data } = await merchantApi.getKeys(); setKeys(data); }
    catch { showToast("Could not load API keys", "error"); }
    finally { setLoading(false); }
  };

  const handleToggleMode = async () => {
    const target = keys.is_test_mode ? "live" : "test";
    setToggling(true);
    try {
      const { data } = await merchantApi.toggleMode(target);
      setKeys(k => ({ ...k, is_test_mode: data.is_test_mode }));
      onModeChange(data.is_test_mode);
      showToast(`Switched to ${data.is_test_mode ? "test" : "live"} mode`, "success");
    } catch (err) {
      const msgs = err.response?.data?.detail;
      showToast(Array.isArray(msgs) ? msgs.join(" ") : msgs || "Mode switch failed", "error");
    } finally { setToggling(false); }
  };

  const handleRotate = async (env) => {
    setRotating(env); setConfirmRotate(null);
    try {
      const { data } = await merchantApi.rotateKey(env);
      setNewKey({ env, key: data.new_secret_key });
      await loadKeys();
      showToast(`${env} secret key rotated`, "success");
    } catch {
      showToast("Key rotation failed", "error");
    } finally { setRotating(null); }
  };

  if (loading) return <div className={styles.loadingText}>Loading keys…</div>;
  if (!keys)   return null;

  const isTest = keys.is_test_mode;

  return (
    <div className={styles.apiKeysSection}>
      {/* Mode toggle */}
      <div className={styles.modeToggleRow}>
        <div className={styles.modeToggleInfo}>
          <div className={styles.modeToggleLabel}>
            Current mode: <ModeBadge isTest={isTest} />
          </div>
          <div className={styles.modeToggleDesc}>
            {isTest
              ? "Test mode — no real payments. Use test keys to build and verify your integration."
              : "Live mode — real payments are active. Buyers are charged for real."}
          </div>
        </div>
        <button
          className={isTest ? styles.goLiveBtn : styles.goTestBtn}
          onClick={handleToggleMode}
          disabled={toggling}
        >
          {toggling ? "Switching…" : isTest ? "Switch to Live mode" : "Switch to Test mode"}
        </button>
      </div>

      {!isTest && (
        <div className={styles.liveWarningBanner}>
          ⚠ You are in <strong>live mode</strong>. Real payments are being processed.
        </div>
      )}

      {/* New key reveal (shown once after rotation) */}
      {newKey && (
        <div className={styles.newKeyReveal}>
          <div className={styles.newKeyHeader}>
            <span className={styles.newKeyTitle}>🔑 New {newKey.env} secret key — save this now</span>
            <button className={styles.newKeyClose} onClick={() => setNewKey(null)}>Dismiss</button>
          </div>
          <p className={styles.newKeyWarning}>This key will not be shown again. Copy it now and store it securely.</p>
          <div className={styles.newKeyBox}>
            <code className={styles.newKeyValue}>{newKey.key}</code>
            <button className={styles.copyBtn} onClick={async () => { await copyToClipboard(newKey.key); showToast("Key copied", "success"); }}>Copy</button>
          </div>
        </div>
      )}

      {/* Key pairs */}
      {[
        {
          env: "test", label: "Test keys",
          pk: keys.test_publishable_key,
          skPrefix: keys.test_secret_key_prefix,
          rotatedAt: keys.test_key_rotated_at,
        },
        {
          env: "live", label: "Live keys",
          pk: keys.live_publishable_key,
          skPrefix: keys.live_secret_key_prefix,
          rotatedAt: keys.live_key_rotated_at,
        },
      ].map(({ env, label, pk, skPrefix, rotatedAt }) => (
        <div key={env} className={`${styles.keyPairCard} ${isTest === (env === "test") ? styles.keyPairActive : styles.keyPairInactive}`}>
          <div className={styles.keyPairHeader}>
            <span className={styles.keyPairLabel}>{label}</span>
            <ModeBadge isTest={env === "test"} />
          </div>

          <div className={styles.keyRow}>
            <span className={styles.keyType}>Publishable key</span>
            <code className={styles.keyValue}>{pk}</code>
            <button className={styles.copyBtn} onClick={async () => { await copyToClipboard(pk); showToast("Copied", "success"); }}>Copy</button>
          </div>

          <div className={styles.keyRow}>
            <span className={styles.keyType}>Secret key</span>
            <code className={styles.keyValue}>{skPrefix}••••••••••••••••••••</code>
            <span className={styles.keyHidden}>hidden</span>
          </div>

          <div className={styles.keyRotateRow}>
            <span className={styles.keyRotatedAt}>
              Last rotated: {date(rotatedAt)}
            </span>
            {confirmRotate === env ? (
              <div className={styles.confirmRotate}>
                <span className={styles.confirmText}>Rotate {env} secret key? Old key invalidated immediately.</span>
                <button className={styles.confirmYes} onClick={() => handleRotate(env)} disabled={rotating === env}>
                  {rotating === env ? "Rotating…" : "Yes, rotate"}
                </button>
                <button className={styles.confirmNo} onClick={() => setConfirmRotate(null)}>Cancel</button>
              </div>
            ) : (
              <button className={styles.rotateBtn} onClick={() => setConfirmRotate(env)}>Rotate secret key</button>
            )}
          </div>
        </div>
      ))}

      <div className={styles.keysFooter}>
        Use your <strong>publishable key</strong> in frontend code. Use your <strong>secret key</strong> on your server only — never expose it publicly.
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ══════════════════════════════════════════════════════════════════════════════
export default function MerchantDashboard() {
  const navigate  = useNavigate();
  const { user, logout } = useAuth();

  const [tab, setTab]               = useState("overview");
  const [merchant, setMerchant]     = useState(null);
  const [loading, setLoading]       = useState(true);
  const [notFound, setNotFound]     = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isTestMode, setIsTestMode] = useState(true);
  const [toasts, setToasts]         = useState([]);
  const toastId                     = useRef(0);

  const showToast = useCallback((msg, type = "success") => {
    const id = ++toastId.current;
    setToasts(p => [...p, { id, msg, type }]);
  }, []);

  // Products
  const [products, setProducts]       = useState([]);
  const [prodLoading, setProdLoading] = useState(false);
  const [showProdForm, setShowProdForm] = useState(false);
  const [editProduct, setEditProduct] = useState(null);

  // Sales
  const [sales, setSales]             = useState([]);
  const [salesLoading, setSalesLoading] = useState(false);
  const [salesFilter, setSalesFilter] = useState("");
  const [salesModeFilter, setSalesModeFilter] = useState(""); // "test" | "live" | ""
  const [selectedSale, setSelectedSale] = useState(null);

  // Automations
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [actions, setActions]         = useState([]);
  const [actionsLoading, setActionsLoading] = useState(false);
  const [showActionForm, setShowActionForm] = useState(false);
  const [editAction, setEditAction]   = useState(null);

  // Analytics
  const [analytics, setAnalytics]     = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsPeriod, setAnalyticsPeriod] = useState("30d");

  // Webhook logs
  const [webhookLogs, setWebhookLogs] = useState([]);
  const [webhookLoading, setWebhookLoading] = useState(false);
  const [webhookFilter, setWebhookFilter] = useState("");

  // Settings
  const [settingsForm, setSettingsForm]     = useState({});
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsTab, setSettingsTab]       = useState("profile"); // "profile" | "keys"

  // ── Bootstrap ───────────────────────────────────────────────────────────────
  useEffect(() => {
    merchantApi.getMe()
      .then(({ data }) => {
        setMerchant(data);
        setSettingsForm(data);
        setIsTestMode(data.is_test_mode ?? true);
      })
      .catch(err => { if (err.response?.status === 404) setNotFound(true); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!merchant) return;
    if (tab === "products" || tab === "automations") loadProducts();
    if (tab === "sales")    loadSales();
    if (tab === "overview") loadAnalytics(analyticsPeriod);
    if (tab === "webhooks") loadWebhookLogs();
  }, [tab, merchant]);

  // ── Loaders ─────────────────────────────────────────────────────────────────
  const loadProducts = async () => {
    setProdLoading(true);
    try { const { data } = await merchantApi.getProducts(); setProducts(data.results ?? data); }
    catch {} finally { setProdLoading(false); }
  };

  const loadSales = async (filter = salesFilter, modeFilter = salesModeFilter) => {
    setSalesLoading(true);
    const params = {};
    if (filter) params.status = filter;
    if (modeFilter === "test") params.is_test = true;
    if (modeFilter === "live") params.is_test = false;
    try { const { data } = await merchantApi.getSales(params); setSales(data.results ?? data); }
    catch {} finally { setSalesLoading(false); }
  };

  const loadActions = async (pid) => {
    setActionsLoading(true);
    try { const { data } = await merchantApi.getActions(pid); setActions(data.results ?? data); }
    catch {} finally { setActionsLoading(false); }
  };

  const loadAnalytics = async (period = analyticsPeriod) => {
    setAnalyticsLoading(true);
    try { const { data } = await merchantApi.getAnalytics(period); setAnalytics(data); }
    catch {} finally { setAnalyticsLoading(false); }
  };

  const loadWebhookLogs = async (filter = webhookFilter) => {
    setWebhookLoading(true);
    const params = filter ? { status: filter } : {};
    try { const { data } = await merchantApi.getWebhookLogs(params); setWebhookLogs(data.results ?? data); }
    catch {} finally { setWebhookLoading(false); }
  };

  // ── Guard ────────────────────────────────────────────────────────────────────
  if (!loading && notFound) return (
    <RegisterScreen showToast={showToast} onDone={(data) => { setMerchant(data); setSettingsForm(data); setNotFound(false); }} />
  );
  if (loading) return <div className={styles.loadingContainer}><div className={styles.spinner} /></div>;

  const goTab = (id) => { setTab(id); setSidebarOpen(false); };
  const checkoutBase = `${window.location.origin}/pay/${merchant?.slug}/`;

  // ════════════════════════════════════════════════════════════════════════════
  return (
    <div className={styles.root}>
      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      <aside className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ""}`}>
        <div className={styles.sidebarHeader}>
          <a href="/dashboard" className={styles.logo}>
            <div className={styles.logoMark}>C</div>
            <span className={styles.logoText}>Merchants</span>
          </a>
        </div>

        {merchant && (
          <div className={styles.merchantCard}>
            <div className={styles.merchantAvatar}>
              {(merchant.business_name || "M")[0].toUpperCase()}
            </div>
            <div className={styles.merchantName}>{merchant.business_name}</div>
            <div className={styles.merchantSlug}>/{merchant.slug}/</div>
            <div className={styles.merchantBadges}>
              {merchant.is_verified
                ? <span className={styles.verifiedPill}>Verified</span>
                : <span className={styles.pendingPill}>Pending review</span>}
              <ModeBadge isTest={isTestMode} />
            </div>
          </div>
        )}

        <nav className={styles.nav}>
          {NAV.map(item => (
            <button
              key={item.id}
              onClick={() => goTab(item.id)}
              className={`${styles.navItem} ${tab === item.id ? styles.navItemActive : ""}`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          <div className={styles.userInfo}>
            <div className={styles.userAvatar}>{(user?.first_name || user?.email || "?")[0].toUpperCase()}</div>
            <div className={styles.userDetails}>
              <div className={styles.userName}>{user?.full_name || user?.email}</div>
              <div className={styles.userRole}>Merchant</div>
            </div>
          </div>
          <button onClick={() => logout().then(() => navigate("/login"))} className={styles.logoutBtn}>Sign out</button>
        </div>
      </aside>

      <button className={styles.menuBtn} onClick={() => setSidebarOpen(true)}>☰</button>
      {sidebarOpen && <div className={styles.overlay} onClick={() => setSidebarOpen(false)} />}

      {/* ── Main ──────────────────────────────────────────────────────────────── */}
      <main className={styles.main}>
        <header className={styles.topbar}>
          <h2 className={styles.topbarTitle}>{NAV.find(n => n.id === tab)?.label}</h2>
          <div className={styles.topbarRight}>
            <ModeBadge isTest={isTestMode} />
            <a href="/dashboard" className={styles.backLink}>Back to CashSpace</a>
          </div>
        </header>

        <div className={styles.content}>

          {/* ── Overview ──────────────────────────────────────────────────────── */}
          {tab === "overview" && (
            <div className={styles.fadeIn}>
              <div className={styles.welcomeHeader}>
                <h3 className={styles.welcomeTitle}>Welcome back{merchant ? `, ${merchant.business_name}` : ""}</h3>
                <p className={styles.welcomeSub}>Here's your merchant overview.</p>
              </div>

              {/* Stats grid */}
              <div className={styles.statsGrid}>
                {[
                  { label: "Total revenue (live)",  value: fmt(merchant?.total_revenue_usd || 0)          },
                  { label: "Total live sales",       value: merchant?.total_sales || 0                     },
                  { label: "Active products",        value: merchant?.product_count || 0                   },
                  { label: "Settlement",             value: `${merchant?.settlement_currency} · ${merchant?.settlement_blockchain}` },
                ].map(s => (
                  <div key={s.label} className={styles.statCard}>
                    <div className={styles.statLabel}>{s.label}</div>
                    <div className={styles.statValue}>{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Analytics chart */}
              <Panel
                title="Revenue"
                action={
                  <div className={styles.periodTabs}>
                    {["7d", "30d", "90d", "1y"].map(p => (
                      <button
                        key={p}
                        className={`${styles.periodTab} ${analyticsPeriod === p ? styles.periodTabActive : ""}`}
                        onClick={() => { setAnalyticsPeriod(p); loadAnalytics(p); }}
                      >{p}</button>
                    ))}
                  </div>
                }
              >
                {analyticsLoading ? (
                  <div className={styles.loadingText}>Loading analytics…</div>
                ) : analytics ? (
                  <>
                    <div className={styles.analyticsTopRow}>
                      <div className={styles.analyticsMetric}>
                        <span className={styles.analyticsValue}>{fmt(analytics.total_revenue_usd)}</span>
                        <span className={styles.analyticsLabel}>revenue</span>
                      </div>
                      <div className={styles.analyticsMetric}>
                        <span className={styles.analyticsValue}>{analytics.total_sales}</span>
                        <span className={styles.analyticsLabel}>sales</span>
                      </div>
                      <div className={styles.analyticsMetric}>
                        <span className={styles.analyticsValue}>{analytics.conversion_rate_pct}%</span>
                        <span className={styles.analyticsLabel}>conversion</span>
                      </div>
                      <div className={styles.analyticsMetric}>
                        <span className={styles.analyticsValue}>{analytics.total_checkouts}</span>
                        <span className={styles.analyticsLabel}>checkouts</span>
                      </div>
                    </div>
                    <SparkChart data={analytics.daily_revenue} />
                    {analytics.top_products?.length > 0 && (
                      <div className={styles.topProducts}>
                        <div className={styles.topProductsTitle}>Top products</div>
                        {analytics.top_products.map(p => (
                          <div key={p.product_id} className={styles.topProductRow}>
                            <span className={styles.topProductName}>{p.product_name}</span>
                            <span className={styles.topProductRevenue}>{fmt(p.revenue)}</span>
                            <span className={styles.topProductSales}>{p.sales} sales</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : null}
              </Panel>

              {/* Checkout link */}
              {merchant && (
                <Panel title="Your checkout link">
                  <div className={styles.checkoutLinkRow}>
                    <div className={styles.checkoutLinkBox}>{checkoutBase}</div>
                    <CopyButton text={checkoutBase} showToast={showToast} />
                  </div>
                  <p className={styles.checkoutHint}>Share this with your audience. Each product gets its own link.</p>
                </Panel>
              )}

              {/* Guide */}
              <div className={styles.guideCard}>
                <div className={styles.guideHeader}>
                  <span className={styles.guideTitle}>Getting started</span>
                </div>
                <div className={styles.guideContent}>
                  <ol className={styles.guideSteps}>
                    <li><strong>Create a product</strong> — go to Products and add what you're selling.</li>
                    <li><strong>Copy the product link</strong> — each product has a URL like <code>/pay/your-shop/product-slug/</code>.</li>
                    <li><strong>Test it</strong> — you're in test mode. Hit "Test sale" on a product to simulate a purchase.</li>
                    <li><strong>Set up automations</strong> — Telegram invite, email, Discord role, webhook.</li>
                    <li><strong>Go live</strong> — switch to Live mode from Settings → API Keys once you're verified.</li>
                  </ol>
                  <p className={styles.guideNote}>Need help? Contact support@cashspace.com</p>
                </div>
              </div>

              {/* Quick actions */}
              <div className={styles.quickActions}>
                {[
                  { label: "Create a product",    desc: "Add a new item for sale",          action: () => { setTab("products"); setShowProdForm(true); } },
                  { label: "View sales",           desc: "See who has paid",                 action: () => goTab("sales") },
                  { label: "Set up automations",   desc: "Auto-add to Telegram, Discord",    action: () => goTab("automations") },
                  { label: "API Keys & Mode",      desc: "Switch test ↔ live, rotate keys",  action: () => { goTab("settings"); setSettingsTab("keys"); } },
                ].map(a => (
                  <button key={a.label} onClick={a.action} className={styles.quickActionBtn}>
                    <div>
                      <div className={styles.quickActionLabel}>{a.label}</div>
                      <div className={styles.quickActionDesc}>{a.desc}</div>
                    </div>
                    <span className={styles.quickArrow}>→</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── Products ──────────────────────────────────────────────────────── */}
          {tab === "products" && (
            <div className={styles.fadeIn}>
              <div className={styles.sectionHeader}>
                <div>
                  <h3 className={styles.sectionTitle}>Products</h3>
                  <p className={styles.sectionSub}>{products.length} product{products.length !== 1 ? "s" : ""}</p>
                </div>
                <button className={styles.primaryBtn} onClick={() => { setEditProduct(null); setShowProdForm(true); }}>New product</button>
              </div>

              {showProdForm && (
                <Panel title={editProduct ? "Edit product" : "New product"}>
                  <ProductForm product={editProduct} showToast={showToast}
                    onCancel={() => { setShowProdForm(false); setEditProduct(null); }}
                    onSave={() => { setShowProdForm(false); setEditProduct(null); loadProducts(); }} />
                </Panel>
              )}

              {prodLoading ? (
                <div className={styles.loadingText}>Loading…</div>
              ) : products.length === 0 && !showProdForm ? (
                <div className={styles.emptyState}>
                  <p className={styles.emptyStateText}>No products yet.</p>
                  <button className={styles.primaryBtn} onClick={() => setShowProdForm(true)}>Create your first product</button>
                </div>
              ) : (
                <div className={styles.productList}>
                  {products.map(p => {
                    const productUrl = `${window.location.origin}/pay/${merchant?.slug}/${p.slug}/`;
                    return (
                      <div key={p.id} className={styles.productCard}>
                        <div className={styles.productHeader}>
                          <div className={styles.productInfo}>
                            <div className={styles.productName}>{p.name}</div>
                            <div className={styles.productBadges}>
                              {!p.is_active  && <span className={styles.inactiveBadge}>INACTIVE</span>}
                              {p.is_sold_out && <span className={styles.soldOutBadge}>SOLD OUT</span>}
                            </div>
                            <div className={styles.productMeta}>
                              <span>{p.product_type_display || p.product_type}</span>
                              <span className={styles.productPrice}>{p.price_usd ? fmt(p.price_usd) : "Buyer chooses"}</span>
                              <span>{p.purchase_count || 0} sales · {fmt(p.revenue_usd || 0)} revenue</span>
                            </div>
                            <div className={styles.productLinkRow}>
                              <div className={styles.productSlug}>{productUrl}</div>
                              <CopyButton text={productUrl} showToast={showToast} />
                            </div>
                          </div>
                          <div className={styles.productActions}>
                            <button className={styles.actionBtn} onClick={() => { setEditProduct(p); setShowProdForm(true); }}>Edit</button>
                            <button
                              className={styles.testSaleBtn}
                              onClick={async () => {
                                try {
                                  await merchantApi.testSale(p.id);
                                  showToast("Test sale created — check Sales CRM", "success");
                                } catch (err) {
                                  showToast(err.response?.data?.detail || "Test sale failed", "error");
                                }
                              }}
                              title="Simulate a complete purchase without real payment"
                            >
                              Test sale
                            </button>
                            <button
                              className={`${styles.actionBtn} ${styles.dangerBtn}`}
                              onClick={async () => {
                                await merchantApi.deleteProduct(p.id);
                                showToast("Product deactivated", "info");
                                loadProducts();
                              }}
                            >
                              Deactivate
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── Sales CRM ─────────────────────────────────────────────────────── */}
          {tab === "sales" && (
            <div className={styles.fadeIn}>
              <div className={styles.salesHeader}>
                <div>
                  <h3 className={styles.sectionTitle}>Sales CRM</h3>
                  <p className={styles.sectionSub}>{sales.length} record{sales.length !== 1 ? "s" : ""}</p>
                </div>
                <div className={styles.salesFilters}>
                  <select
                    className={styles.filterSelect}
                    value={salesFilter}
                    onChange={e => { setSalesFilter(e.target.value); loadSales(e.target.value, salesModeFilter); }}
                  >
                    <option value="">All statuses</option>
                    <option value="completed">Completed</option>
                    <option value="payment_created">Awaiting payment</option>
                    <option value="initiated">Initiated</option>
                    <option value="abandoned">Abandoned</option>
                  </select>
                  <select
                    className={styles.filterSelect}
                    value={salesModeFilter}
                    onChange={e => { setSalesModeFilter(e.target.value); loadSales(salesFilter, e.target.value); }}
                  >
                    <option value="">All modes</option>
                    <option value="live">Live only</option>
                    <option value="test">Test only</option>
                  </select>
                  <button className={styles.actionBtn} onClick={() => loadSales()}>Refresh</button>
                </div>
              </div>

              {salesLoading ? (
                <div className={styles.loadingText}>Loading…</div>
              ) : sales.length === 0 ? (
                <div className={styles.emptyState}>No sales yet. Share your checkout link to start.</div>
              ) : (
                <div className={styles.salesTableWrapper}>
                  <table className={styles.salesTable}>
                    <thead>
                      <tr>
                        <th>Buyer</th><th>Product</th><th>Amount</th><th>Mode</th><th>Status</th><th>Automation</th><th>Date</th><th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {sales.map(s => (
                        <tr key={s.id} className={styles.saleRow} onClick={() => setSelectedSale(s)}>
                          <td>
                            <div className={styles.buyerEmail}>{s.email}</div>
                            {s.telegram_username && <div className={styles.buyerTelegram}>@{s.telegram_username}</div>}
                          </td>
                          <td className={styles.productNameCell}>{s.product_name}</td>
                          <td className={styles.productPrice}>{fmt(s.amount_usd)}</td>
                          <td><ModeBadge isTest={s.is_test} /></td>
                          <td><StatusBadge status={s.status} /></td>
                          <td>{s.automation_triggered
                            ? <span className={styles.automationDone}>Done</span>
                            : <span className={styles.automationPending}>Pending</span>}
                          </td>
                          <td className={styles.dateCell}>{date(s.created_at)}</td>
                          <td>
                            <button className={styles.actionBtn} onClick={e => { e.stopPropagation(); setSelectedSale(s); }}>View</button>
                            {s.status === "completed" && !s.automation_triggered && (
                              <button
                                className={styles.retriggerBtn}
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  try { await merchantApi.retrigger(s.id); showToast("Automation re-queued", "success"); }
                                  catch { showToast("Retrigger failed", "error"); }
                                }}
                              >Re-fire</button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Sale detail modal */}
              {selectedSale && (
                <div className={styles.modalOverlay} onClick={() => setSelectedSale(null)}>
                  <div className={styles.modal} onClick={e => e.stopPropagation()}>
                    <div className={styles.modalHeader}>
                      <h3 className={styles.modalTitle}>Sale details</h3>
                      <button onClick={() => setSelectedSale(null)} className={styles.modalClose}>×</button>
                    </div>
                    {[
                      ["Mode",          <ModeBadge key="m" isTest={selectedSale.is_test} />],
                      ["Email",         selectedSale.email],
                      ["Full name",     selectedSale.full_name || "—"],
                      ["Product",       selectedSale.product_name],
                      ["Amount",        fmt(selectedSale.amount_usd)],
                      ["Telegram",      selectedSale.telegram_username ? `@${selectedSale.telegram_username}` : "—"],
                      ["Discord",       selectedSale.discord_username || "—"],
                      ["Phone",         selectedSale.phone_number || "—"],
                      ["Custom field",  selectedSale.custom_field_value || "—"],
                      ["Status",        <StatusBadge key="s" status={selectedSale.status} />],
                      ["Payment",       <StatusBadge key="ps" status={selectedSale.payment_status} />],
                      ["Automation",    selectedSale.automation_triggered ? "Done" : "Pending"],
                      ["Date",          date(selectedSale.created_at)],
                    ].map(([k, v]) => (
                      <div key={k} className={styles.modalRow}>
                        <span className={styles.modalLabel}>{k}</span>
                        <span className={styles.modalValue}>{v}</span>
                      </div>
                    ))}
                    {selectedSale.automation_error && (
                      <div className={styles.modalError}>Automation error: {selectedSale.automation_error}</div>
                    )}
                    {selectedSale.status === "completed" && (
                      <button
                        className={styles.modalRetriggerBtn}
                        onClick={async () => {
                          try { await merchantApi.retrigger(selectedSale.id); showToast("Automation re-queued", "success"); setSelectedSale(null); }
                          catch { showToast("Retrigger failed", "error"); }
                        }}
                      >Re-fire automation</button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Automations ───────────────────────────────────────────────────── */}
          {tab === "automations" && (
            <div className={styles.fadeIn}>
              <div className={styles.sectionHeader}>
                <div>
                  <h3 className={styles.sectionTitle}>Post-Payment Automations</h3>
                  <p className={styles.sectionSub}>Configure what happens automatically when a buyer completes payment.</p>
                </div>
              </div>
              <Panel title="Select a product to configure">
                {prodLoading ? <div className={styles.loadingText}>Loading products…</div> : (
                  <div className={styles.productSelectList}>
                    {products.map(p => (
                      <button
                        key={p.id}
                        onClick={() => { setSelectedProduct(p); loadActions(p.id); setShowActionForm(false); setEditAction(null); }}
                        className={`${styles.productSelectBtn} ${selectedProduct?.id === p.id ? styles.productSelectBtnActive : ""}`}
                      >
                        <div className={styles.productSelectInfo}>
                          <div className={styles.productSelectName}>{p.name}</div>
                          <div className={styles.productSelectMeta}>{p.purchase_count || 0} sales</div>
                        </div>
                        <span className={styles.productSelectArrow}>{selectedProduct?.id === p.id ? "Selected" : "Configure"}</span>
                      </button>
                    ))}
                    {products.length === 0 && <div className={styles.emptyStateSmall}>No products yet. Create a product first.</div>}
                  </div>
                )}
              </Panel>

              {selectedProduct && (
                <Panel
                  title={`Actions for "${selectedProduct.name}"`}
                  action={<button className={styles.primaryBtnSmall} onClick={() => { setEditAction(null); setShowActionForm(true); }}>Add action</button>}
                >
                  {showActionForm && (
                    <div className={styles.actionFormContainer}>
                      <ActionForm
                        action={editAction}
                        productId={selectedProduct.id}
                        showToast={showToast}
                        onCancel={() => { setShowActionForm(false); setEditAction(null); }}
                        onSave={() => { setShowActionForm(false); setEditAction(null); loadActions(selectedProduct.id); }}
                      />
                    </div>
                  )}
                  {actionsLoading ? <div className={styles.loadingText}>Loading…</div> :
                   actions.length === 0 && !showActionForm ? (
                    <div className={styles.emptyStateSmall}>No actions yet. Add one to automate access delivery.</div>
                  ) : (
                    <div className={styles.actionsList}>
                      {actions.map(a => (
                        <div key={a.id} className={styles.actionItem}>
                          <div>
                            <div className={styles.actionType}>
                              <span className={styles.actionTypeName}>
                                {{ telegram_invite: "Telegram invite", email_delivery: "Email delivery", webhook: "Webhook", discord_role: "Discord role" }[a.action_type] || a.action_type}
                              </span>
                              {!a.is_active && <span className={styles.disabledBadge}>DISABLED</span>}
                            </div>
                            <div className={styles.actionPriority}>Priority {a.priority}</div>
                          </div>
                          <div className={styles.actionItemButtons}>
                            <button className={styles.actionBtn} onClick={() => { setEditAction(a); setShowActionForm(true); }}>Edit</button>
                            <button
                              className={`${styles.actionBtn} ${styles.dangerBtn}`}
                              onClick={async () => {
                                await merchantApi.deleteAction(selectedProduct.id, a.id);
                                showToast("Action deleted", "info");
                                loadActions(selectedProduct.id);
                              }}
                            >Delete</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Panel>
              )}
            </div>
          )}

          {/* ── Webhook Logs ──────────────────────────────────────────────────── */}
          {tab === "webhooks" && (
            <div className={styles.fadeIn}>
              <div className={styles.salesHeader}>
                <div>
                  <h3 className={styles.sectionTitle}>Webhook Logs</h3>
                  <p className={styles.sectionSub}>Every outgoing webhook attempt to your server, with retry history.</p>
                </div>
                <div className={styles.salesFilters}>
                  <select
                    className={styles.filterSelect}
                    value={webhookFilter}
                    onChange={e => { setWebhookFilter(e.target.value); loadWebhookLogs(e.target.value); }}
                  >
                    <option value="">All statuses</option>
                    <option value="success">Success</option>
                    <option value="failed">Failed</option>
                    <option value="retrying">Retrying</option>
                    <option value="exhausted">Exhausted</option>
                    <option value="pending">Pending</option>
                  </select>
                  <button className={styles.actionBtn} onClick={() => loadWebhookLogs()}>Refresh</button>
                </div>
              </div>

              {webhookLoading ? (
                <div className={styles.loadingText}>Loading…</div>
              ) : webhookLogs.length === 0 ? (
                <div className={styles.emptyState}>No webhook deliveries yet. Configure a webhook URL on a product action or in Settings.</div>
              ) : (
                <div className={styles.salesTableWrapper}>
                  <table className={styles.salesTable}>
                    <thead>
                      <tr>
                        <th>Event</th><th>Endpoint</th><th>Status</th><th>HTTP</th><th>Duration</th><th>Mode</th><th>Attempts</th><th>Date</th><th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {webhookLogs.map(log => (
                        <tr key={log.id} className={styles.saleRow}>
                          <td><code className={styles.eventType}>{log.event_type}</code></td>
                          <td className={styles.endpointCell} title={log.endpoint_url}>
                            {log.endpoint_url.length > 40 ? log.endpoint_url.slice(0, 40) + "…" : log.endpoint_url}
                          </td>
                          <td><StatusBadge status={log.status} /></td>
                          <td>
                            {log.response_status_code
                              ? <span className={log.response_status_code < 300 ? styles.httpOk : styles.httpError}>{log.response_status_code}</span>
                              : <span className={styles.httpError}>—</span>}
                          </td>
                          <td>{log.duration_ms != null ? `${log.duration_ms}ms` : "—"}</td>
                          <td><ModeBadge isTest={log.is_test} /></td>
                          <td>{log.attempt_number} / {5}</td>
                          <td className={styles.dateCell}>{date(log.created_at)}</td>
                          <td>
                            {log.can_retry && (
                              <button
                                className={styles.retriggerBtn}
                                onClick={async () => {
                                  try { await merchantApi.retryWebhook(log.id); showToast("Retry queued", "success"); loadWebhookLogs(); }
                                  catch { showToast("Retry failed", "error"); }
                                }}
                              >Retry</button>
                            )}
                            {log.error_message && (
                              <span className={styles.errorTooltip} title={log.error_message}>⚠</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Settings ──────────────────────────────────────────────────────── */}
          {tab === "settings" && (
            <div className={styles.fadeIn}>
              <div className={styles.sectionHeader}>
                <div>
                  <h3 className={styles.sectionTitle}>Settings</h3>
                  <p className={styles.sectionSub}>Business profile and API configuration.</p>
                </div>
              </div>

              {/* Settings sub-tabs */}
              <div className={styles.settingsSubTabs}>
                {[{ id: "profile", label: "Business profile" }, { id: "keys", label: "API Keys & Mode" }].map(st => (
                  <button
                    key={st.id}
                    className={`${styles.settingsSubTab} ${settingsTab === st.id ? styles.settingsSubTabActive : ""}`}
                    onClick={() => setSettingsTab(st.id)}
                  >{st.label}</button>
                ))}
              </div>

              {settingsTab === "profile" && (
                <Panel title="Business profile">
                  <form
                    onSubmit={async (e) => {
                      e.preventDefault(); setSettingsSaving(true);
                      try {
                        const { data } = await merchantApi.update(settingsForm);
                        setMerchant(data); showToast("Settings saved", "success");
                      } catch { showToast("Save failed", "error"); }
                      finally { setSettingsSaving(false); }
                    }}
                    className={styles.settingsForm}
                  >
                    <Field label="Business name"><input className={styles.input} value={settingsForm.business_name || ""} onChange={e => setSettingsForm(f => ({ ...f, business_name: e.target.value }))} required /></Field>
                    <Field label="Description"><textarea className={styles.textarea} value={settingsForm.description || ""} onChange={e => setSettingsForm(f => ({ ...f, description: e.target.value }))} /></Field>
                    <Field label="Logo URL"><input className={styles.input} value={settingsForm.logo_url || ""} onChange={e => setSettingsForm(f => ({ ...f, logo_url: e.target.value }))} placeholder="https://..." /></Field>
                    <div className={styles.rowTwo}>
                      <Field label="Settlement blockchain">
                        <select className={styles.select} value={settingsForm.settlement_blockchain || "TRX"} onChange={e => setSettingsForm(f => ({ ...f, settlement_blockchain: e.target.value }))}>
                          <option value="TRX">Tron (TRX)</option><option value="ETH">Ethereum (ETH)</option>
                          <option value="BTC">Bitcoin (BTC)</option><option value="BASE">Base</option><option value="POL">Polygon</option>
                        </select>
                      </Field>
                      <Field label="Settlement currency">
                        <select className={styles.select} value={settingsForm.settlement_currency || "USDT"} onChange={e => setSettingsForm(f => ({ ...f, settlement_currency: e.target.value }))}>
                          <option value="USDT">USDT</option><option value="USDC">USDC</option>
                          <option value="BTC">BTC</option><option value="ETH">ETH</option><option value="TRX">TRX</option>
                        </select>
                      </Field>
                    </div>
                    <Field label="Settlement wallet address"><input className={styles.input} value={settingsForm.settlement_wallet_address || ""} onChange={e => setSettingsForm(f => ({ ...f, settlement_wallet_address: e.target.value }))} placeholder="Where your payouts land" /></Field>
                    <Field label="Webhook URL (optional)" hint="POST notification on every completed payment"><input className={styles.input} value={settingsForm.webhook_url || ""} onChange={e => setSettingsForm(f => ({ ...f, webhook_url: e.target.value }))} placeholder="https://your-server.com/webhook" /></Field>
                    <Field label="Webhook secret (optional)"><input className={styles.input} value={settingsForm.webhook_secret || ""} onChange={e => setSettingsForm(f => ({ ...f, webhook_secret: e.target.value }))} placeholder="Signing secret" /></Field>
                    <div className={styles.settingsFooter}>
                      <div className={styles.slugInfo}>Slug: <code className={styles.slugCode}>/{merchant?.slug}/</code> (immutable)</div>
                      <button type="submit" className={styles.saveSettingsBtn} disabled={settingsSaving}>{settingsSaving ? "Saving…" : "Save settings"}</button>
                    </div>
                  </form>
                </Panel>
              )}

              {settingsTab === "keys" && (
                <Panel title="API Keys & Mode">
                  <APIKeysPanel
                    merchant={merchant}
                    showToast={showToast}
                    onModeChange={(isTest) => setIsTestMode(isTest)}
                  />
                </Panel>
              )}
            </div>
          )}

        </div>
      </main>

      {/* ── Toasts ────────────────────────────────────────────────────────────── */}
      <div className={styles.toastContainer}>
        {toasts.map(t => (
          <Toast key={t.id} msg={t.msg} type={t.type} onClose={() => setToasts(p => p.filter(x => x.id !== t.id))} />
        ))}
      </div>
    </div>
  );
}