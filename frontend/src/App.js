// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';

// Public pages
import LandingPage from './pages/LandingPage/LandingPage';
import LoginPage from './pages/Auth/LoginPage';
import RegisterPage from './pages/Auth/RegisterPage';
import ForgotPasswordPage from './pages/Auth/ForgotPasswordPage';
import ResetPasswordPage from './pages/Auth/ResetPasswordPage';
import VerifyEmailPage from './pages/Auth/VerifyEmailPage';
import MerchantCheckoutPage from './pages/Checkout/MerchantCheckoutPage';
import CheckoutStatusPage from './pages/Checkout/CheckoutStatusPage';
import PublicAssetPage from './pages/Creator/PublicAssetPage';

// Protected
import UnifiedDashboard from './pages/UnifiedDashboard';
import PaymentPage from './pages/Payment/PaymentPage';
import PaymentDetailPage from './pages/Payment/PaymentDetailsPage';
import ProfilePage from './pages/Profile/ProfilePage';
import NotFoundPage from './pages/NotFound/NotFoundPage';
import MerchantDashboard from './pages/Merchant/MerchantDashboard';
import MerchantRegister from './pages/Merchant/MerchantRegister';
import CreatorDashboard from './pages/Creator/CreatorDashboard';
import CreatorRegister from './pages/Creator/CreatorRegister';
import CreateAsset from './pages/Creator/CreateAsset';
import EditAsset from './pages/Creator/EditAsset';
import CreatorSales from './pages/Creator/CreatorSales';
import CreatorSettings from './pages/Creator/CreatorSettings';
import AdminUsersPage from './pages/Admin/AdminUsersPage';
import AdminPaymentsPage from './pages/Admin/AdminPaymentsPage';
import AdminAuditLogsPage from './pages/Admin/AdminAuditLogsPage';
import AdminMerchants from './pages/Admin/AdminMerchants';
import AdminCreators from './pages/Admin/AdminCreators';
import PayoutHistory from './pages/PayoutHistory/PayoutHistory';

import ProtectedRoute from './components/auth/ProtectedRoute';
import AdminRoute from './components/auth/AdminRoute';

function App() {
  return (
    <Router>
      <Routes>
        {/* Public */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/pay/:merchantSlug/" element={<MerchantCheckoutPage />} />
        <Route path="/pay/:merchantSlug/:productSlug/" element={<MerchantCheckoutPage />} />
        <Route path="/pay/:merchantSlug/:productSlug/status/:checkoutId/" element={<CheckoutStatusPage />} />
        <Route path="/creator/pay/:slug/" element={<PublicAssetPage />} />

        {/* Protected – core */}
        <Route path="/dashboard" element={<ProtectedRoute><UnifiedDashboard /></ProtectedRoute>} />
        <Route path="/buy" element={<ProtectedRoute><PaymentPage /></ProtectedRoute>} />
        <Route path="/history" element={<ProtectedRoute><PaymentPage /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
        <Route path="/payment" element={<ProtectedRoute><PaymentPage /></ProtectedRoute>} />
        <Route path="/payment/:id" element={<ProtectedRoute><PaymentDetailPage /></ProtectedRoute>} />
        <Route path="/payouts" element={<ProtectedRoute><PayoutHistory /></ProtectedRoute>} />

        {/* Redirects */}
        <Route path="/wallets" element={<Navigate to="/profile" replace />} />
        <Route path="/settings" element={<Navigate to="/profile" replace />} />

        {/* Merchant & Creator */}
        <Route path="/merchant" element={<ProtectedRoute><MerchantDashboard /></ProtectedRoute>} />
        <Route path="/merchant/register" element={<ProtectedRoute><MerchantRegister /></ProtectedRoute>} />
        <Route path="/creator" element={<ProtectedRoute><CreatorDashboard /></ProtectedRoute>} />
        <Route path="/creator/register" element={<ProtectedRoute><CreatorRegister /></ProtectedRoute>} />
        <Route path="/creator/assets/new" element={<ProtectedRoute><CreateAsset /></ProtectedRoute>} />
        <Route path="/creator/assets/:id" element={<ProtectedRoute><EditAsset /></ProtectedRoute>} />
        <Route path="/creator/sales" element={<ProtectedRoute><CreatorSales /></ProtectedRoute>} />
        <Route path="/creator/settings" element={<ProtectedRoute><CreatorSettings /></ProtectedRoute>} />

        {/* Admin */}
        <Route path="/admin/users" element={<AdminRoute><AdminUsersPage /></AdminRoute>} />
        <Route path="/admin/payments" element={<AdminRoute><AdminPaymentsPage /></AdminRoute>} />
        <Route path="/admin/audit-logs" element={<AdminRoute><AdminAuditLogsPage /></AdminRoute>} />
        <Route path="/admin/merchants" element={<AdminRoute><AdminMerchants /></AdminRoute>} />
        <Route path="/admin/creators" element={<AdminRoute><AdminCreators /></AdminRoute>} />

        {/* Legacy / catch-all */}
        <Route path="/old-dashboard" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Router>
  );
}

export default App;