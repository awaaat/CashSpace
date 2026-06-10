// src/hooks/useDashboardData.js
import { useState, useEffect } from 'react';
import { useAuth } from './useAuth';
import { authApi } from '../api/auth';
import { creatorApi } from '../api/creator';
import { merchantApi } from '../api/merchant';
import { usePayments } from './usePayment';

export function useDashboardData() {
  const { user } = useAuth();
  const { payments, fetchPayments } = usePayments();
  const [data, setData] = useState({
    wallets: [],
    hasMerchant: false,
    hasCreator: false,
    merchantStats: null,
    creatorStats: null,
    notifications: [],
    unreadCount: 0,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      try {
        const [walletsRes, creatorRes, merchantRes, creatorStatsRes, merchantStatsRes, notifRes, unreadRes] = await Promise.allSettled([
          authApi.getCryptoWallets(),
          creatorApi.getProfile(),
          merchantApi.getMe(),
          creatorApi.getStats(),
          merchantApi.getStats?.() || Promise.resolve({ data: null }),
          authApi.getNotifications({ page: 1, page_size: 5 }),
          authApi.getUnreadNotificationCount(),
        ]);

        const wallets = walletsRes.status === 'fulfilled' ? (walletsRes.value.data?.results || walletsRes.value.data || []) : [];
        const hasCreator = creatorRes.status === 'fulfilled' && !!creatorRes.value.data;
        const hasMerchant = merchantRes.status === 'fulfilled' && !!merchantRes.value.data;
        const creatorStats = creatorStatsRes.status === 'fulfilled' ? creatorStatsRes.value.data : null;
        const merchantStats = merchantStatsRes.status === 'fulfilled' ? merchantStatsRes.value.data : null;
        const notifications = notifRes.status === 'fulfilled' ? (notifRes.value.data.results || []) : [];
        const unreadCount = unreadRes.status === 'fulfilled' ? unreadRes.value.data.unread_count : 0;

        if (isMounted) {
          setData({
            wallets,
            hasMerchant,
            hasCreator,
            merchantStats,
            creatorStats,
            notifications,
            unreadCount,
            loading: false,
            error: null,
          });
        }

        await fetchPayments();
      } catch (err) {
        if (isMounted) {
          setData(prev => ({ ...prev, loading: false, error: 'Failed to load dashboard data' }));
        }
      }
    };

    load();
    return () => { isMounted = false; };
  }, [fetchPayments]);

  return { data, loading: data.loading, payments, error: data.error, refetch: () => {} };
}