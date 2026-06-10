import React, { useEffect, useRef, useState } from "react";

// ─── YOUR IMAGES ─────────────────────────────────────────────────────────────
import gifImage        from "./landing_page_gif.gif";
import img1            from "./landing_page_image_1.png";
import img3            from "./landing_page_image_3.jpg";
import img4            from "./Landing_page_image_4.webp";
import img5            from "./landing_page_image_5.webp";

// ─── Palette ──────────────────────────────────────────────────────────────────
const G = {
  bg:        "#0A0C10",
  bgCard:    "#111520",
  bgCardAlt: "#161B28",
  border:    "rgba(255,255,255,0.07)",
  amber:     "#F5A623",
  amberDim:  "#C4831A",
  amberGlow: "rgba(245,166,35,0.15)",
  red:       "#E84545",
  green:     "#2ECC71",
  white:     "#F0F2F8",
  muted:     "#6B7280",
  mutedMid:  "#9CA3AF",
};

// ─── Global keyframes injected once ──────────────────────────────────────────
const KEYFRAMES = `
  @keyframes tickerScroll {
    0%   { transform: translateX(0); }
    100% { transform: translateX(-50%); }
  }
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes shimmer {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
  }
`;

const css = {
  root: {
    background: G.bg,
    color: G.white,
    fontFamily: "'Inter', 'Helvetica Neue', Arial, sans-serif",
    minHeight: "100vh",
    overflowX: "hidden",
    position: "relative",
  },

  // ── NAV ──
  nav: {
    position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 2rem", height: "64px",
    background: "rgba(10,12,16,0.85)",
    backdropFilter: "blur(12px)",
    borderBottom: `1px solid ${G.border}`,
  },
  logo: {
    display: "flex", alignItems: "center", gap: "0.5rem",
    textDecoration: "none", color: G.white,
  },
  logoMark: {
    width: "28px", height: "28px",
    background: G.amber,
    borderRadius: "8px",
    display: "flex", alignItems: "center", justifyContent: "center",
    fontWeight: 800, fontSize: "0.85rem", color: "#000",
  },
  logoText: { fontWeight: 700, fontSize: "0.95rem", letterSpacing: "-0.02em" },
  navLinks: { display: "flex", gap: "1.5rem" },
  navLink: {
    color: G.mutedMid, textDecoration: "none",
    fontSize: "0.8rem", fontWeight: 500,
    transition: "color 0.2s",
  },
  navActions: { display: "flex", gap: "0.6rem", alignItems: "center" },
  btnGhost: {
    padding: "0.4rem 0.9rem",
    border: `1px solid ${G.border}`,
    borderRadius: "8px",
    color: G.white, textDecoration: "none",
    fontSize: "0.75rem", fontWeight: 500,
    background: "transparent", cursor: "pointer",
  },
  btnPrimary: {
    padding: "0.4rem 1rem",
    background: G.amber,
    borderRadius: "8px",
    color: "#000", textDecoration: "none",
    fontSize: "0.75rem", fontWeight: 700,
    display: "inline-flex", alignItems: "center", gap: "0.3rem",
    cursor: "pointer", border: "none",
  },

  // ── TICKER ──
  tickerWrap: {
    marginTop: "64px",
    background: G.bgCard,
    borderBottom: `1px solid ${G.border}`,
    overflow: "hidden",
    height: "36px",
    display: "flex", alignItems: "center",
  },

  // ── HERO (text side) ──
  heroBadge: {
    display: "inline-flex", alignItems: "center", gap: "0.4rem",
    background: G.amberGlow,
    border: `1px solid ${G.amberDim}`,
    borderRadius: "999px",
    padding: "0.2rem 0.7rem",
    fontSize: "0.7rem", fontWeight: 600, color: G.amber,
    marginBottom: "1rem",
  },
  badgeDot: {
    width: "5px", height: "5px",
    borderRadius: "50%", background: G.amber,
    boxShadow: `0 0 4px ${G.amber}`,
  },
  heroTitle: {
    fontSize: "clamp(2rem, 3.8vw, 3.2rem)",
    fontWeight: 800,
    lineHeight: 1.1,
    letterSpacing: "-0.03em",
    margin: "0 0 0.8rem",
  },
  heroAccent: { color: G.amber },
  heroDesc: {
    fontSize: "0.9rem", color: G.mutedMid,
    lineHeight: 1.6, maxWidth: "460px",
    margin: "0 0 1.5rem",
  },
  heroCTA: { display: "flex", gap: "0.8rem", flexWrap: "wrap", alignItems: "center" },
  btnHero: {
    display: "inline-flex", alignItems: "center", gap: "0.3rem",
    background: G.amber, color: "#000",
    padding: "0.6rem 1.2rem",
    borderRadius: "8px", fontWeight: 700,
    fontSize: "0.85rem", textDecoration: "none",
    border: "none", cursor: "pointer",
  },
  btnSecondary: {
    display: "inline-flex", alignItems: "center", gap: "0.3rem",
    color: G.mutedMid, textDecoration: "none",
    fontSize: "0.8rem",
  },

  // ── REJECTION VISUAL ──
  rejectionCard: {
    background: G.bgCard,
    border: `1px solid ${G.border}`,
    borderRadius: "20px",
    padding: "2rem",
    position: "relative",
    overflow: "hidden",
  },
  rejectionRow: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0.8rem 1rem",
    borderRadius: "10px",
    marginBottom: "0.7rem",
    fontSize: "0.85rem", fontWeight: 600,
  },

  // ── PROOF STRIP ──
  proofStrip: {
    borderTop: `1px solid ${G.border}`,
    borderBottom: `1px solid ${G.border}`,
    padding: "2rem",
    background: G.bgCard,
  },
  proofInner: {
    maxWidth: "1100px", margin: "0 auto",
    display: "flex", justifyContent: "space-around",
    flexWrap: "wrap", gap: "1.5rem",
    textAlign: "center",
  },
  proofStat:  { display: "flex", flexDirection: "column", gap: "0.2rem" },
  proofVal:   { fontSize: "1.8rem", fontWeight: 800, color: G.amber, letterSpacing: "-0.02em" },
  proofLabel: { fontSize: "0.7rem", color: G.muted, fontWeight: 500 },

  // ── SECTIONS ──
  section: { padding: "3rem 2rem", maxWidth: "1100px", margin: "0 auto" },
  sectionLabel: {
    display: "inline-block",
    fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.12em",
    textTransform: "uppercase", color: G.amber,
    marginBottom: "0.75rem",
  },
  sectionTitle: {
    fontSize: "clamp(1.5rem, 2.8vw, 2.2rem)",
    fontWeight: 800, letterSpacing: "-0.03em",
    lineHeight: 1.2, margin: "0 0 0.75rem",
  },
  sectionDesc: {
    fontSize: "0.85rem", color: G.mutedMid,
    lineHeight: 1.6, maxWidth: "540px", margin: "0 0 2rem",
  },

  // ── NICHE GRID ──
  nicheGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
    gap: "1rem",
  },
  nicheCard: {
    background: G.bgCard,
    border: `1px solid ${G.border}`,
    borderRadius: "14px",
    padding: "1.25rem",
    transition: "border-color 0.2s, transform 0.2s",
  },
  nicheIcon:  { fontSize: "1.5rem", marginBottom: "0.5rem" },
  nicheTitle: { fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.3rem" },
  nicheDesc:  { fontSize: "0.75rem", color: G.muted, lineHeight: 1.5 },
  nichePain: {
    marginTop: "0.6rem",
    fontSize: "0.7rem", color: G.red,
    background: "rgba(232,69,69,0.08)",
    padding: "0.2rem 0.5rem",
    borderRadius: "6px",
    display: "inline-block", fontWeight: 600,
  },

  // ── HOW IT WORKS ──
  howGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "1rem",
  },
  howCard: {
    background: G.bgCard,
    border: `1px solid ${G.border}`,
    borderRadius: "14px",
    padding: "1.25rem",
    position: "relative",
  },
  howNum:   { fontSize: "0.6rem", fontWeight: 800, letterSpacing: "0.1em", color: G.amber, marginBottom: "0.75rem", textTransform: "uppercase" },
  howTitle: { fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.3rem" },
  howDesc:  { fontSize: "0.75rem", color: G.muted, lineHeight: 1.5 },

  // ── COMPARE ──
  compareWrap: {
    background: G.bgCard,
    border: `1px solid ${G.border}`,
    borderRadius: "16px",
    overflow: "hidden",
    marginTop: "1.5rem",
  },
  compareRow: {
    display: "grid",
    gridTemplateColumns: "2fr 1fr 1fr",
    padding: "0.7rem 1.2rem",
    borderBottom: `1px solid ${G.border}`,
    fontSize: "0.8rem",
    alignItems: "center",
  },
  compareHeader: {
    background: G.bgCardAlt,
    fontWeight: 700, fontSize: "0.7rem",
    letterSpacing: "0.06em", textTransform: "uppercase",
  },

  // ── CTA ──
  ctaSection: { padding: "3rem 2rem", textAlign: "center", position: "relative" },
  ctaGlow: {
    position: "absolute", top: "50%", left: "50%",
    transform: "translate(-50%, -50%)",
    width: "400px", height: "200px",
    background: G.amberGlow,
    borderRadius: "50%",
    filter: "blur(60px)",
    pointerEvents: "none",
  },
  ctaTitle: {
    fontSize: "clamp(1.6rem, 3.2vw, 2.4rem)",
    fontWeight: 800, letterSpacing: "-0.03em",
    lineHeight: 1.2, margin: "0 0 0.75rem",
    position: "relative",
  },
  ctaDesc: {
    color: G.mutedMid, fontSize: "0.85rem",
    margin: "0 auto 1.8rem", maxWidth: "460px",
    position: "relative",
  },
  ctaButtons: {
    display: "flex", gap: "0.8rem",
    justifyContent: "center", flexWrap: "wrap",
    position: "relative",
  },

  // ── FOOTER ──
  footer: {
    borderTop: `1px solid ${G.border}`,
    padding: "2rem 2rem",
    background: G.bgCard,
  },
  footerInner: {
    maxWidth: "1100px", margin: "0 auto",
    display: "flex", justifyContent: "space-between",
    flexWrap: "wrap", gap: "1.5rem",
  },
  footerBottom: {
    maxWidth: "1100px", margin: "1rem auto 0",
    paddingTop: "1rem",
    borderTop: `1px solid ${G.border}`,
    display: "flex", justifyContent: "space-between",
    flexWrap: "wrap", gap: "0.75rem",
    fontSize: "0.7rem", color: G.muted,
  },
};

// ─── Rejection Ticker ─────────────────────────────────────────────────────────
function RejectionTicker() {
  const items = [
    { text: "Stripe rejected your account", bad: true },
    { text: "PayPal froze your funds", bad: true },
    { text: "Bank declined merchant services", bad: true },
    { text: "CashSpace accepted you", bad: false },
    { text: "Stripe rejected your account", bad: true },
    { text: "PayPal froze your funds", bad: true },
    { text: "Your processor shut you down", bad: true },
    { text: "CashSpace accepted you", bad: false },
    { text: "Stripe rejected your account", bad: true },
    { text: "Your subscription billing broke", bad: true },
    { text: "CashSpace accepted you", bad: false },
  ];

  return (
    <div style={css.tickerWrap}>
      <div style={{
        display: "flex", gap: "0",
        animation: "tickerScroll 28s linear infinite",
        whiteSpace: "nowrap",
      }}>
        {[...items, ...items].map((item, i) => (
          <span key={i} style={{
            padding: "0 2rem",
            fontSize: "0.7rem", fontWeight: 600,
            color: item.bad ? G.red : G.green,
            letterSpacing: "0.02em",
            borderRight: `1px solid ${G.border}`,
            height: "36px",
            display: "inline-flex", alignItems: "center", gap: "0.4rem",
          }}>
            <span>{item.bad ? "✕" : "✓"}</span>
            {item.text}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Rejection Visual ─────────────────────────────────────────────────────────
function RejectionVisual() {
  const processors = [
    { name: "Stripe",    status: "rejected", icon: "S" },
    { name: "PayPal",    status: "rejected", icon: "P" },
    { name: "Banks",     status: "rejected", icon: "B" },
    { name: "CashSpace", status: "accepted", icon: "C" },
  ];

  return (
    <div style={css.rejectionCard}>
      <div style={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: G.muted, marginBottom: "1rem" }}>
        Payment processor status
      </div>
      {processors.map((p) => (
        <div key={p.name} style={{
          ...css.rejectionRow,
          background: p.status === "accepted" ? "rgba(46,204,113,0.08)" : "rgba(232,69,69,0.06)",
          border: `1px solid ${p.status === "accepted" ? "rgba(46,204,113,0.25)" : "rgba(232,69,69,0.15)"}`,
          marginBottom: "0.7rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
            <div style={{
              width: "28px", height: "28px", borderRadius: "8px",
              background: p.status === "accepted" ? G.amber : "rgba(255,255,255,0.06)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontWeight: 800, fontSize: "0.7rem",
              color: p.status === "accepted" ? "#000" : G.muted,
            }}>{p.icon}</div>
            <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{p.name}</span>
          </div>
          <span style={{
            fontWeight: 700, fontSize: "0.7rem",
            color: p.status === "accepted" ? G.green : G.red,
            background: p.status === "accepted" ? "rgba(46,204,113,0.12)" : "rgba(232,69,69,0.12)",
            padding: "0.2rem 0.6rem", borderRadius: "999px",
          }}>
            {p.status === "accepted" ? "✓ Accepted" : "✕ Rejected"}
          </span>
        </div>
      ))}
      <div style={{
        marginTop: "1rem", padding: "0.8rem 1rem",
        background: G.amberGlow, border: `1px solid ${G.amberDim}`,
        borderRadius: "10px", fontSize: "0.75rem", color: G.amber, fontWeight: 600,
      }}>
        ⚡ Your buyers pay with local fiat. You settle in USDT. No restrictions.
      </div>
    </div>
  );
}

// ─── Counter ──────────────────────────────────────────────────────────────────
function Counter({ to, suffix = "", prefix = "" }) {
  const [val, setVal] = useState(0);
  const ref = useRef(null);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      let start = 0;
      const step = Math.ceil(to / 60);
      const id = setInterval(() => {
        start = Math.min(start + step, to);
        setVal(start);
        if (start >= to) clearInterval(id);
      }, 16);
    }, { threshold: 0.5 });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [to]);
  return <span ref={ref}>{prefix}{val.toLocaleString()}{suffix}</span>;
}

// ─── BENTO GRID (distributed image layout) ───────────────────────────────────
function BentoGrid() {
  const [hovered, setHovered] = useState(null);

  const cells = [
    // Large feature cell — img1
    {
      id: 0, src: img1, alt: "Dashboard",
      style: { gridColumn: "span 2", gridRow: "span 2", minHeight: "320px" },
      label: "Real-time dashboard",
    },
    // Tall right cell — img3
    {
      id: 1, src: img3, alt: "Analytics",
      style: { gridColumn: "span 1", gridRow: "span 2", minHeight: "320px" },
      label: "Fiat → crypto settlement",
    },
    // Wide bottom-left — img4
    {
      id: 2, src: img4, alt: "Mobile",
      style: { gridColumn: "span 1", gridRow: "span 1", minHeight: "180px" },
      label: "Works on any device",
    },
    // Square bottom-middle — img5
    {
      id: 3, src: img5, alt: "Billing",
      style: { gridColumn: "span 1", gridRow: "span 1", minHeight: "180px" },
      label: "Automated billing",
    },
    // Live GIF — square bottom-right
    {
      id: 4, src: gifImage, alt: "Live demo",
      style: { gridColumn: "span 1", gridRow: "span 1", minHeight: "180px" },
      label: "See it live",
    },
  ];

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gridTemplateRows: "auto",
      gap: "12px",
      width: "100%",
    }}>
      {cells.map((cell) => (
        <div
          key={cell.id}
          style={{
            ...cell.style,
            position: "relative",
            borderRadius: "16px",
            overflow: "hidden",
            border: `1px solid ${hovered === cell.id ? G.amber : G.border}`,
            cursor: "pointer",
            transition: "border-color 0.25s, transform 0.25s",
            transform: hovered === cell.id ? "scale(1.015)" : "scale(1)",
          }}
          onMouseEnter={() => setHovered(cell.id)}
          onMouseLeave={() => setHovered(null)}
        >
          <img
            src={cell.src}
            alt={cell.alt}
            style={{
              width: "100%", height: "100%",
              objectFit: "cover",
              display: "block",
              transition: "transform 0.4s ease",
              transform: hovered === cell.id ? "scale(1.04)" : "scale(1)",
            }}
            loading="lazy"
          />
          {/* Overlay label */}
          <div style={{
            position: "absolute", bottom: 0, left: 0, right: 0,
            padding: "2rem 1rem 0.9rem",
            background: "linear-gradient(to top, rgba(10,12,16,0.85) 0%, transparent 100%)",
            opacity: hovered === cell.id ? 1 : 0,
            transition: "opacity 0.25s",
          }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: G.white }}>
              {cell.label}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── CINEMATIC FEATURE SECTION ────────────────────────────────────────────────
function CinematicSection() {
  return (
    <div style={{
      position: "relative",
      width: "100%",
      overflow: "hidden",
      borderTop: `1px solid ${G.border}`,
      borderBottom: `1px solid ${G.border}`,
    }}>
      {/* Full-width background image */}
      <img
        src={img4}
        alt="CashSpace platform"
        style={{
          width: "100%",
          height: "480px",
          objectFit: "cover",
          objectPosition: "center",
          display: "block",
          filter: "brightness(0.3)",
        }}
        loading="lazy"
      />

      {/* Layered overlapping images */}
      <img
        src={img5}
        alt=""
        aria-hidden="true"
        style={{
          position: "absolute",
          bottom: "-30px", right: "6%",
          width: "clamp(220px, 28vw, 380px)",
          borderRadius: "16px",
          border: `1px solid ${G.border}`,
          boxShadow: "0 32px 80px rgba(0,0,0,0.7)",
          objectFit: "cover",
          height: "260px",
        }}
      />
      <img
        src={img1}
        alt=""
        aria-hidden="true"
        style={{
          position: "absolute",
          bottom: "20px", right: "calc(6% + clamp(220px,28vw,380px) - 80px)",
          width: "clamp(160px, 20vw, 280px)",
          borderRadius: "16px",
          border: `1px solid rgba(245,166,35,0.3)`,
          boxShadow: "0 24px 60px rgba(0,0,0,0.6)",
          objectFit: "cover",
          height: "180px",
        }}
      />

      {/* Text overlay */}
      <div style={{
        position: "absolute",
        top: "50%", left: "6%",
        transform: "translateY(-50%)",
        maxWidth: "480px",
      }}>
        <div style={{
          fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.12em",
          textTransform: "uppercase", color: G.amber, marginBottom: "1rem",
        }}>
          The infrastructure
        </div>
        <h2 style={{
          fontSize: "clamp(1.8rem, 3.5vw, 2.8rem)",
          fontWeight: 800, letterSpacing: "-0.03em",
          lineHeight: 1.1, margin: "0 0 1rem", color: G.white,
        }}>
          Built to run<br />
          <span style={{ color: G.amber }}>without friction.</span>
        </h2>
        <p style={{
          fontSize: "0.9rem", color: G.mutedMid, lineHeight: 1.65,
          margin: "0 0 1.75rem",
        }}>
          Payments accepted in 40+ countries. Every transaction converts and
          settles to USDT automatically. No manual steps, no frozen accounts.
        </p>
        <a href="/register" style={css.btnHero}>
          <span>Start now</span>
          <span>↗</span>
        </a>
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const niches = [
    {
      icon: "📈",
      title: "Forex Educators & Signal Providers",
      desc: "Run VIP Telegram groups or sell trading signals globally. Collect subscriptions automatically — no more chasing screenshots.",
      pain: "Stripe bans & manual USDT headaches",
    },
    {
      icon: "🎲",
      title: "Betting & Prediction Communities",
      desc: "Tipsters, betting analysts, and prediction markets. Accept payments from members in any country, settle without processor interference.",
      pain: "Processors terminate accounts overnight",
    },
    {
      icon: "🔞",
      title: "Adult Creators with Own Platforms",
      desc: "You built your own fanbase — don't give 20% to a platform. Accept subscriptions and one-time payments on your terms.",
      pain: "Mainstream processors restrict or ban",
    },
    {
      icon: "₿",
      title: "Crypto Tools & Services",
      desc: "SaaS, bots, analytics, and signals. Sell globally without worrying about which payment processor will tolerate you this month.",
      pain: "Banks & processors flag crypto businesses",
    },
  ];

  const howSteps = [
    { n: "Step 1", title: "Create your merchant account", desc: "Sign up and configure your business in under 5 minutes. No complex onboarding." },
    { n: "Step 2", title: "Generate a payment link",      desc: "Create a checkout page, subscription link, or QR code for your product or community." },
    { n: "Step 3", title: "Your buyer pays in fiat",      desc: "M-Pesa, card, bank transfer — your customers pay with what they already have." },
    { n: "Step 4", title: "You receive USDT",             desc: "CashSpace handles conversion and settlement. Your wallet receives USDT. Automatically." },
  ];

  const compareRows = [
    { feature: "Accept global fiat payments",    cashspace: true,  stripe: false },
    { feature: "Serve forex / trading niches",   cashspace: true,  stripe: false },
    { feature: "Serve betting communities",      cashspace: true,  stripe: false },
    { feature: "Adult creator payments",         cashspace: true,  stripe: false },
    { feature: "Crypto settlement",              cashspace: true,  stripe: false },
    { feature: "Automated subscription access", cashspace: true,  stripe: true  },
    { feature: "No account freeze risk",         cashspace: true,  stripe: false },
  ];

  return (
    <div style={css.root}>
      <style>{KEYFRAMES}</style>

      {/* ── NAV ── */}
      <nav style={{ ...css.nav, boxShadow: scrolled ? "0 1px 20px rgba(0,0,0,0.4)" : "none" }}>
        <a href="/" style={css.logo}>
          <div style={css.logoMark}>C</div>
          <span style={css.logoText}>CashSpace</span>
        </a>
        <div style={css.navLinks}>
          <a href="#who"     style={css.navLink}>Who it's for</a>
          <a href="#how"     style={css.navLink}>How it works</a>
          <a href="#compare" style={css.navLink}>Compare</a>
        </div>
        <div style={css.navActions}>
          <a href="/login"    style={css.btnGhost}>Sign in</a>
          <a href="/register" style={css.btnPrimary}>Get started →</a>
        </div>
      </nav>

      {/* ── TICKER ── */}
      <RejectionTicker />

      {/* ── HERO ── left: copy  |  right: hero image + RejectionVisual stacked ── */}
      <section style={{ padding: "4rem 2rem 3rem", maxWidth: "1200px", margin: "0 auto" }}>
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
          gap: "3rem", alignItems: "start",
        }}>
          {/* Left — copy */}
          <div>
            <div style={css.heroBadge}>
              <span style={css.badgeDot} />
              Built for businesses Stripe won't touch
            </div>
            <h1 style={css.heroTitle}>
              Your buyers pay.<br />
              <span style={css.heroAccent}>You get paid.</span><br />
              No exceptions.
            </h1>
            <p style={css.heroDesc}>
              CashSpace is the payment platform for high-risk digital businesses.
              Forex educators, betting communities, adult creators — if traditional processors
              reject you, we're built for you.
            </p>
            <div style={css.heroCTA}>
              <a href="/register" style={css.btnHero}>
                <span>Start accepting payments</span>
                <span>↗</span>
              </a>
              <a href="#who" style={css.btnSecondary}>See who it's for →</a>
            </div>
            <div style={{ marginTop: "1.5rem", display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
              {[
                { val: "~2 min", label: "Settlement time" },
                { val: "3%",     label: "Transaction fee" },
                { val: "USDT",   label: "You receive" },
              ].map((m) => (
                <div key={m.label}>
                  <div style={{ fontWeight: 800, fontSize: "0.9rem", color: G.amber }}>{m.val}</div>
                  <div style={{ fontSize: "0.65rem", color: G.muted, fontWeight: 500 }}>{m.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right — large hero image ON TOP, RejectionVisual below */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{
              borderRadius: "20px",
              overflow: "hidden",
              border: `1px solid ${G.border}`,
              height: "240px",
            }}>
              <img
                src={img3}
                alt="CashSpace platform preview"
                style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
              />
            </div>
            <RejectionVisual />
          </div>
        </div>
      </section>

      {/* ── PROOF STRIP ── */}
      <div style={css.proofStrip}>
        <div style={css.proofInner}>
          {[
            { val: 48200, suffix: "+",    label: "Payments processed" },
            { val: 99,    suffix: ".9%",  label: "Uptime" },
            { val: 120,   suffix: "+",    label: "Active merchants" },
            { val: 2,     suffix: " min", label: "Avg. settlement" },
          ].map((s) => (
            <div key={s.label} style={css.proofStat}>
              <div style={css.proofVal}><Counter to={s.val} suffix={s.suffix} /></div>
              <div style={css.proofLabel}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── BENTO GRID IMAGE SECTION ── */}
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "4rem 2rem" }}>
        <div style={{ marginBottom: "2rem" }}>
          <span style={css.sectionLabel}>Platform</span>
          <h2 style={css.sectionTitle}>Every tool you need,<br />none of the friction.</h2>
        </div>
        <BentoGrid />
      </div>

      {/* ── WHO IT'S FOR ── with gif contextually embedded ── */}
      <section id="who" style={css.section}>
        <span style={css.sectionLabel}>Who it's for</span>
        <h2 style={css.sectionTitle}>
          Built for businesses<br />
          traditional processors <span style={{ color: G.red }}>reject.</span>
        </h2>
        <p style={css.sectionDesc}>
          If Stripe, PayPal, or your bank has ever frozen your account, rejected your application,
          or made collecting payments a nightmare — CashSpace was built for you.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.5rem", alignItems: "start" }}>
          <div style={css.nicheGrid}>
            {niches.map((n) => (
              <div key={n.title} style={css.nicheCard}>
                <div style={css.nicheIcon}>{n.icon}</div>
                <div style={css.nicheTitle}>{n.title}</div>
                <div style={css.nicheDesc}>{n.desc}</div>
                <div style={css.nichePain}>✕ {n.pain}</div>
              </div>
            ))}
          </div>
          {/* GIF contextually placed alongside niche cards */}
          <div style={{
            borderRadius: "16px", overflow: "hidden",
            border: `1px solid ${G.border}`,
            gridColumn: "1 / -1",
            height: "260px",
          }}>
            <img
              src={gifImage}
              alt="CashSpace live demo"
              style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
            />
          </div>
        </div>
      </section>

      {/* ── CINEMATIC FEATURE SECTION ── */}
      <CinematicSection />

      {/* ── HOW IT WORKS ── */}
      <section id="how" style={{
        ...css.section,
        background: G.bgCard,
        maxWidth: "100%",
        borderTop: `1px solid ${G.border}`,
        borderBottom: `1px solid ${G.border}`,
      }}>
        <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "0 2rem" }}>
          <span style={css.sectionLabel}>How it works</span>
          <h2 style={css.sectionTitle}>Four steps.<br />Your buyers pay fiat. You receive crypto.</h2>
          <div style={css.howGrid}>
            {howSteps.map((s) => (
              <div key={s.n} style={css.howCard}>
                <div style={css.howNum}>{s.n}</div>
                <h3 style={css.howTitle}>{s.title}</h3>
                <p style={css.howDesc}>{s.desc}</p>
              </div>
            ))}
          </div>
          <div style={{
            marginTop: "2rem",
            background: G.bgCardAlt,
            border: `1px solid ${G.border}`,
            borderRadius: "12px",
            padding: "1rem 1.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.8rem",
            flexWrap: "wrap",
            fontSize: "0.8rem",
            fontWeight: 600,
          }}>
            {[
              { label: "Customer",       sub: "Pays with M-Pesa / Card" },
              "→",
              { label: "CashSpace",      sub: "Converts & settles", highlight: true },
              "→",
              { label: "You",            sub: "Receive USDT" },
              "→",
              { label: "Access granted", sub: "Automatically" },
            ].map((item, i) =>
              item === "→" ? (
                <span key={i} style={{ color: G.muted, fontSize: "1rem" }}>→</span>
              ) : (
                <div key={i} style={{
                  textAlign: "center",
                  padding: "0.5rem 1rem",
                  borderRadius: "8px",
                  background: item.highlight ? G.amberGlow : "rgba(255,255,255,0.04)",
                  border: `1px solid ${item.highlight ? G.amberDim : G.border}`,
                  minWidth: "100px",
                }}>
                  <div style={{ color: item.highlight ? G.amber : G.white }}>{item.label}</div>
                  <div style={{ color: G.muted, fontWeight: 400, fontSize: "0.7rem", marginTop: "0.1rem" }}>{item.sub}</div>
                </div>
              )
            )}
          </div>
        </div>
      </section>

      {/* ── COMPARE ── */}
      <section id="compare" style={css.section}>
        <span style={css.sectionLabel}>Compare</span>
        <h2 style={css.sectionTitle}>Why not just<br />use Stripe?</h2>
        <p style={css.sectionDesc}>
          Stripe is great — until it isn't. If your business operates in a niche
          that traditional processors flag, you need infrastructure built for you.
        </p>
        <div style={css.compareWrap}>
          <div style={{ ...css.compareRow, ...css.compareHeader }}>
            <span>Feature</span>
            <span style={{ textAlign: "center", color: G.amber }}>CashSpace</span>
            <span style={{ textAlign: "center", color: G.muted }}>Stripe / PayPal</span>
          </div>
          {compareRows.map((row) => (
            <div key={row.feature} style={css.compareRow}>
              <span style={{ fontSize: "0.75rem" }}>{row.feature}</span>
              <span style={{ textAlign: "center", color: G.green, fontWeight: 700 }}>{row.cashspace ? "✓" : "✕"}</span>
              <span style={{ textAlign: "center", color: row.stripe ? G.green : G.red, fontWeight: 700 }}>{row.stripe ? "✓" : "✕"}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={css.ctaSection}>
        <div style={css.ctaGlow} />
        <span style={{ ...css.sectionLabel, position: "relative" }}>Get started</span>
        <h2 style={css.ctaTitle}>
          Stop letting payment processors<br />
          <span style={{ color: G.amber }}>control your revenue.</span>
        </h2>
        <p style={css.ctaDesc}>
          Set up your CashSpace merchant account in minutes. Start accepting payments
          from your audience worldwide — regardless of your niche.
        </p>
        <div style={css.ctaButtons}>
          <a href="/register" style={css.btnHero}>
            <span>Create merchant account</span>
            <span>↗</span>
          </a>
          <a href="/login" style={{ ...css.btnGhost, padding: "0.6rem 1.2rem" }}>Sign in instead</a>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer style={css.footer}>
        <div style={css.footerInner}>
          <div>
            <a href="/" style={css.logo}>
              <div style={css.logoMark}>C</div>
              <span style={css.logoText}>CashSpace</span>
            </a>
            <p style={{ color: G.muted, fontSize: "0.7rem", marginTop: "0.5rem", maxWidth: "200px" }}>
              The payment layer for digital businesses that traditional processors won't serve.
            </p>
          </div>
          <div style={{ display: "flex", gap: "2.5rem", flexWrap: "wrap" }}>
            {[
              { head: "Product", links: ["How it works", "Who it's for", "Compare"] },
              { head: "Account", links: ["Sign up", "Sign in", "Dashboard"] },
              { head: "Legal",   links: ["Privacy Policy", "Terms of Use", "Risk Disclosure"] },
            ].map((col) => (
              <div key={col.head} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: G.muted }}>{col.head}</span>
                {col.links.map((l) => (
                  <a key={l} href="#" style={{ color: G.mutedMid, textDecoration: "none", fontSize: "0.7rem" }}>{l}</a>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div style={css.footerBottom}>
          <span>© 2026 CashSpace. All rights reserved.</span>
          <span>Not a bank. Crypto involves risk. Not available in all jurisdictions.</span>
        </div>
      </footer>
    </div>
  );
}