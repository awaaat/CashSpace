// frontend/src/api/gating.js
import api from "./axios";

export const gatingApi = {
  // Public asset (no auth)
  getAsset: (slug) => api.get(`/gating/assets/${slug}/`),
  checkout: (slug, data) => api.post(`/gating/assets/${slug}/checkout/`, data),
  getCheckoutStatus: (grantId) => api.get(`/gating/checkout/${grantId}/status/`),

  // Unlock & embed
  unlock: (token) => api.get(`/gating/unlock/${token}/`),
  getEmbedContent: (token) => api.get(`/gating/embed/${token}/`),

  // Token verification (external)
  verifyToken: (token) => api.post("/gating/verify-token/", { token }),
  verifyBatch: (tokens) => api.post("/gating/verify-batch/", { tokens }),
  introspectToken: (token) => api.post("/gating/introspect/", { token }),
  verifyTokenLegacy: (token) => api.get(`/gating/verify-token-legacy/?token=${token}`),

  // Proxy & file download
  proxy: (token, extraPath = "") => api.get(`/gating/proxy/${token}/${extraPath}`),
  download: (token) => api.get(`/gating/download/${token}/`),

  // Grant status (for buyers)
  getGrantStatus: (grantId, email) => api.get(`/gating/grants/${grantId}/status/`, { params: { email } }),
  resendAccess: (grantId, email) => api.post(`/gating/grants/${grantId}/resend/`, { email }),

  // Affiliate
  generateAffiliateCode: () => api.post("/gating/affiliate/generate/"),
  affiliateClick: (code, assetId, redirect) => api.get("/gating/affiliate/click/", { params: { code, asset_id: assetId, redirect } }),

  // Discount validation (public)
  validateDiscount: (code, assetSlug, amount) => api.post("/gating/discount/validate/", { code, asset_slug: assetSlug, amount }),

  // Webhook (internal, usually not called from frontend)
  // webhook: (data) => api.post("/gating/webhook/", data),

  // Authenticated (creator/merchant) endpoints
  getMyAssets: () => api.get("/gating/my/assets/"),
  getMyAsset: (id) => api.get(`/gating/my/assets/${id}/`),
  getMyAssetStats: (id) => api.get(`/gating/my/assets/${id}/stats/`),
  updateMyAsset: (id, data) => api.patch(`/gating/my/assets/${id}/`, data),
  deleteMyAsset: (id) => api.delete(`/gating/my/assets/${id}/`),
  createMyAsset: (data) => api.post("/gating/my/assets/", data), // matches MyAssetsListView POST
  getMyGrants: () => api.get("/gating/my/grants/"),
  getMyAffiliateStats: () => api.get("/gating/my/affiliate/"),

  // ViewSet endpoints (if you use router)
  listAssets: (params) => api.get("/gating/assets/", { params }),
  retrieveAsset: (id) => api.get(`/gating/assets/${id}/`),
  duplicateAsset: (id) => api.post(`/gating/assets/${id}/duplicate/`),
  listGrants: (params) => api.get("/gating/grants/", { params }),
  revokeGrant: (id) => api.post(`/gating/grants/${id}/revoke/`),
  listDiscountCodes: (params) => api.get("/gating/discount-codes/", { params }),
  createDiscountCode: (data) => api.post("/gating/discount-codes/", data),
  updateDiscountCode: (id, data) => api.patch(`/gating/discount-codes/${id}/`, data),
  deleteDiscountCode: (id) => api.delete(`/gating/discount-codes/${id}/`),
  // Nested: grants under asset
  getAssetGrants: (assetId, params) => api.get(`/gating/assets/${assetId}/grants/`, { params }),
};