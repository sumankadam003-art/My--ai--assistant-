import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import API_URL from '../apiConfig';

type ActionItem = { name: string; description: string; risk: string; required_permissions: string[]; requires_approval: boolean; enabled: boolean };

export default function ActionsScreen() {
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Neha uses her backend identity. Review each action before approving.');

  const loadActions = useCallback(async () => {
    if (!API_URL) throw new Error('API address is not configured.');
    const response = await fetch(`${API_URL}/actions`);
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Could not load actions.');
    setActions(Array.isArray(data.actions) ? data.actions : []);
  }, []);

  useEffect(() => {
    let active = true;
    void loadActions().then(() => { if (active) setMessage('Actions loaded. Choose an action to review.'); })
      .catch(error => { if (active) setMessage(error instanceof Error ? error.message : 'Could not load actions.'); });
    return () => { active = false; };
  }, [loadActions]);

  async function approveAndRun(action: ActionItem) {
    if (!API_URL) return;
    setBusy(true);
    try {
      const approvalResponse = await fetch(`${API_URL}/actions/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action.name, arguments: {}, owner_confirmed: true }),
      });
      const approval = await approvalResponse.json();
      if (!approvalResponse.ok || !approval.success || !approval.approval_token) throw new Error(approval.error || 'Approval could not be issued.');
      const executionResponse = await fetch(`${API_URL}/actions/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action.name, arguments: {}, approval_token: approval.approval_token }),
      });
      const result = await executionResponse.json();
      if (!executionResponse.ok) throw new Error(result.error || 'Action request failed.');
      const detail = result.status === 'executed_unverified'
        ? `${result.message} The handler returned; the physical result was not independently verified.`
        : result.message || result.status || 'No result was returned.';
      setMessage(`${action.description}: ${detail}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Action failed.');
    } finally { setBusy(false); }
  }

  function confirmAction(action: ActionItem) {
    Alert.alert('Confirm device action',
      `Neha is requesting permission to: ${action.description}\n\nPermission: ${action.required_permissions.join(', ')}\nRisk: ${action.risk.toUpperCase()}\n\nDo you want to run it now?`,
      [{ text: 'Cancel', style: 'cancel' }, { text: 'Approve & Run', onPress: () => { void approveAndRun(action); } }]);
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.container}>
        <Text style={s.title}>NEHA ACTION CONTROL</Text>
        <Text style={s.subtitle}>Backend-managed identity · explicit action approval</Text>
        <View style={s.statusCard}>
          <Text style={s.statusTitle}>NEHA SYSTEM IDENTITY</Text>
          <Text style={s.statusText}>{message}</Text>
          <TouchableOpacity style={s.secondary} onPress={() => { void loadActions().catch(e => setMessage(e.message)); }} disabled={busy}>
            <Text style={s.secondaryText}>REFRESH ACTIONS</Text>
          </TouchableOpacity>
        </View>
        {actions.map(action => (
          <View key={action.name} style={s.actionCard}>
            <View style={s.actionHeading}><Text style={s.actionName}>{action.description}</Text><Text style={s.risk}>{action.risk.toUpperCase()}</Text></View>
            <Text style={s.permission}>Permission: {action.required_permissions.join(', ')}</Text>
            <TouchableOpacity style={[s.primary, !action.enabled && s.disabled]} disabled={busy || !action.enabled} onPress={() => confirmAction(action)}>
              <Text style={s.primaryText}>{action.enabled ? 'REVIEW & APPROVE' : 'DISABLED'}</Text>
            </TouchableOpacity>
          </View>
        ))}
        {actions.length === 0 && <Text style={s.hint}>No actions are registered or the backend is not configured.</Text>}
        {busy && <ActivityIndicator style={s.loader} color="#8DDCFF" />}
        <Text style={s.footer}>Keep Neha's API bound to localhost. Never put the Supabase service-role key in this app.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#05080D' }, container: { padding: 18, paddingBottom: 36 },
  title: { color: '#F1F7FF', fontSize: 20, fontWeight: '900', letterSpacing: 2 },
  subtitle: { color: '#8CB8D1', fontSize: 11, marginTop: 6, marginBottom: 18 },
  statusCard: { backgroundColor: '#0D1A27', borderColor: '#31546D', borderWidth: 1, borderRadius: 14, padding: 14, marginBottom: 16 },
  statusTitle: { color: '#8DDAFF', fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  statusText: { color: '#EAF4FC', fontSize: 13, lineHeight: 19, marginTop: 7 },
  primary: { backgroundColor: '#8DDCFF', borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 13 },
  primaryText: { color: '#06111C', fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  secondary: { backgroundColor: '#173047', borderColor: '#4B7797', borderWidth: 1, borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 13 },
  secondaryText: { color: '#BDEBFF', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  hint: { color: '#90A4B7', fontSize: 11, lineHeight: 17, marginTop: 13 },
  actionCard: { backgroundColor: '#0B131E', borderColor: '#2B4356', borderWidth: 1, borderRadius: 14, padding: 14, marginBottom: 11 },
  actionHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  actionName: { color: '#F1F7FF', fontSize: 14, fontWeight: '800', flex: 1 },
  risk: { color: '#FFD18A', fontSize: 9, fontWeight: '900', marginLeft: 8 },
  permission: { color: '#8FA9BD', fontSize: 10, marginTop: 8 }, disabled: { opacity: 0.45 },
  loader: { marginTop: 16 }, footer: { color: '#71899E', fontSize: 10, lineHeight: 16, marginTop: 20 },
});
