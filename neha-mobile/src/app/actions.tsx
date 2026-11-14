import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Linking, Modal, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import API_URL from '../apiConfig';
import * as SMS from 'expo-sms';
import { getAccessToken, getChallenge, login, logout } from '../auth';

type ActionItem = { name: string; description: string; risk: string; required_permissions: string[]; requires_approval: boolean; enabled: boolean };

export default function ActionsScreen() {
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Login is required to view protected actions.');
  const [loginVisible, setLoginVisible] = useState(false);
  const [challengeId, setChallengeId] = useState('');
  const [challengeNumber, setChallengeNumber] = useState('');
  const [answer, setAnswer] = useState('');
  const [loginError, setLoginError] = useState('');
  const [smsRecipient, setSmsRecipient] = useState('');
  const [smsMessage, setSmsMessage] = useState('');

  const loadActions = useCallback(async () => {
    if (!API_URL) throw new Error('API address is not configured.');
    const token = await getAccessToken();
    if (!token) {
      const challenge = await getChallenge();
      setChallengeId(challenge.challengeId);
      setChallengeNumber(challenge.challenge);
      setLoginVisible(true);
      setMessage('Unlock Neha to view protected actions.');
      return;
    }
    const response = await fetch(`${API_URL}/actions`, { headers: { Authorization: `Bearer ${token}` } });
    const data = await response.json();
    if (response.status === 401) {
      await logout();
      const challenge = await getChallenge();
      setChallengeId(challenge.challengeId);
      setChallengeNumber(challenge.challenge);
      setLoginVisible(true);
      setMessage('Your session expired. Sign in again.');
      return;
    }
    if (!response.ok || !data.success) throw new Error(data.error || 'Could not load actions.');
    setActions(Array.isArray(data.actions) ? data.actions : []);
  }, []);

  useEffect(() => {
    let active = true;
    void loadActions().then(() => { if (active) setMessage('Actions loaded. Choose an action to review.'); })
      .catch(error => { if (active) setMessage(error instanceof Error ? error.message : 'Could not load actions.'); });
    return () => { active = false; };
  }, [loadActions]);

  async function approveAndRun(action: ActionItem, actionArguments: Record<string, string> = {}) {
    if (!API_URL) return;
    setBusy(true);
    try {
      const token = await getAccessToken();
      if (!token) throw new Error('Login required. Refresh and sign in.');
      const approvalResponse = await fetch(`${API_URL}/actions/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ action: action.name, arguments: actionArguments, owner_confirmed: true }),
      });
      const approval = await approvalResponse.json();
      if (!approvalResponse.ok || !approval.success || !approval.approval_token) throw new Error(approval.error || 'Approval could not be issued.');
      const executionResponse = await fetch(`${API_URL}/actions/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ action: action.name, arguments: actionArguments, approval_token: approval.approval_token }),
      });
      const result = await executionResponse.json();
      if (!executionResponse.ok) throw new Error(result.error || 'Action request failed.');
      const approvedUrls: Record<string, string> = {
        'open youtube': 'https://www.youtube.com',
        'open google': 'https://www.google.com',
        'open gmail': 'https://mail.google.com',
        'open maps': 'https://maps.google.com',
        'open instagram': 'https://www.instagram.com',
      };

      const expectedUrl = approvedUrls[action.name];
      if (
        result.status === 'executed_unverified' &&
        action.name === 'send_sms' &&
        result.sms_payload &&
        result.sms_payload.recipient === actionArguments.recipient &&
        result.sms_payload.message === actionArguments.message
      ) {
        const available = await SMS.isAvailableAsync();
        if (!available) throw new Error('No SMS app is available on this device.');
        const smsResult = await SMS.sendSMSAsync(
          [result.sms_payload.recipient],
          result.sms_payload.message,
        );
        setMessage(smsResult.result === 'cancelled'
          ? 'SMS composer was cancelled. No message was sent from this flow.'
          : 'SMS composer opened. Review the recipient and message, then press Send. Android does not report delivery status to Neha.');
        return;
      }
      if (
        result.status === 'executed_unverified' &&
        expectedUrl &&
        result.launch_url === expectedUrl
      ) {
        await Linking.openURL(expectedUrl);
        setMessage(`${action.description}: Opened ${expectedUrl}`);
        return;
      }

      const detail = result.status === 'executed_unverified'
        ? `${result.message} The handler returned; the physical result was not independently verified.`
        : result.message || result.status || 'No result was returned.';
      setMessage(`${action.description}: ${detail}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Action failed.');
    } finally { setBusy(false); }
  }

  async function submitLogin() {
    try {
      await login(challengeId, answer);
      setLoginVisible(false);
      setLoginError('');
      await loadActions();
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Login failed.');
    }
  }

  function confirmAction(action: ActionItem) {
    if (action.name === 'send_sms') {
      const recipient = smsRecipient.trim();
      const messageText = smsMessage;
      const normalizedRecipient = recipient.replaceAll(' ', '').replaceAll('-', '').replaceAll('(', '').replaceAll(')', '');
      const digits = normalizedRecipient.startsWith('+') ? normalizedRecipient.slice(1) : normalizedRecipient;
      const phoneValid = /^[1-9][0-9]{6,14}$/.test(digits) &&
        (normalizedRecipient === digits || normalizedRecipient === `+${digits}`);
      if (!phoneValid || !messageText.trim() || messageText.length > 1600) {
        setMessage('Enter a valid phone number and a message of 1–1600 characters.');
        return;
      }
      Alert.alert('Review SMS details',
        `Recipient: ${recipient}

Message:
${messageText}

Neha will open your phone’s SMS app. You must review and press Send there.`,
        [{ text: 'Cancel', style: 'cancel' }, { text: 'Continue to SMS app', onPress: () => { void approveAndRun(action, { recipient, message: messageText }); } }]);
      return;
    }
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
            {action.name === 'send_sms' && (
              <View style={s.smsForm}>
                <Text style={s.smsLabel}>RECIPIENT PHONE NUMBER</Text>
                <TextInput value={smsRecipient} onChangeText={setSmsRecipient} keyboardType="phone-pad" autoComplete="tel" placeholder="+91 9876543210" placeholderTextColor="#7799B2" style={s.smsInput} maxLength={20} />
                <Text style={s.smsLabel}>MESSAGE (MAX 1600 CHARACTERS)</Text>
                <TextInput value={smsMessage} onChangeText={setSmsMessage} multiline textAlignVertical="top" placeholder="Write your message..." placeholderTextColor="#7799B2" style={[s.smsInput, s.smsMessage]} maxLength={1600} />
                <Text style={s.smsCount}>{smsMessage.length}/1600</Text>
              </View>
            )}
            <TouchableOpacity style={[s.primary, !action.enabled && s.disabled]} disabled={busy || !action.enabled} onPress={() => confirmAction(action)}>
              <Text style={s.primaryText}>{action.enabled ? 'REVIEW & APPROVE' : 'DISABLED'}</Text>
            </TouchableOpacity>
          </View>
        ))}
        {actions.length === 0 && <Text style={s.hint}>No actions are registered or the backend is not configured.</Text>}
        {busy && <ActivityIndicator style={s.loader} color="#8DDCFF" />}
        <Text style={s.footer}>Keep Neha's API bound to localhost. Never put the Supabase service-role key in this app.</Text>
      </ScrollView>
        <Modal visible={loginVisible} transparent animationType="fade" onRequestClose={() => setLoginVisible(false)}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.82)', justifyContent: 'center', padding: 24 }}>
            <View style={{ backgroundColor: '#101D2A', borderColor: '#5CBFFF', borderWidth: 1, borderRadius: 18, padding: 20 }}>
              <Text style={{ color: '#EAF6FF', fontSize: 18, fontWeight: '800' }}>NEHA OWNER LOGIN</Text>
              <Text style={{ color: '#A9DFFF', fontSize: 15, marginTop: 14 }}>Challenge: {challengeNumber}</Text>
              <TextInput value={answer} onChangeText={setAnswer} keyboardType="number-pad" placeholder="Enter response" placeholderTextColor="#7799B2" style={{ color: '#FFFFFF', borderColor: '#38546A', borderWidth: 1, borderRadius: 10, padding: 12, marginTop: 14 }} />
              {!!loginError && <Text style={{ color: '#FF9B9B', marginTop: 10 }}>{loginError}</Text>}
              <TouchableOpacity onPress={() => { void submitLogin(); }} style={{ backgroundColor: '#8DDCFF', padding: 13, borderRadius: 10, alignItems: 'center', marginTop: 16 }}>
                <Text style={{ color: '#06111C', fontWeight: '900' }}>UNLOCK</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setLoginVisible(false)} style={{ padding: 12, alignItems: 'center' }}><Text style={{ color: '#A9DFFF' }}>CANCEL</Text></TouchableOpacity>
            </View>
          </View>
        </Modal>

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
  smsForm: { marginTop: 14, gap: 8 }, smsLabel: { color: '#8DDAFF', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  smsInput: { color: '#FFFFFF', backgroundColor: '#07101A', borderColor: '#38546A', borderWidth: 1, borderRadius: 9, padding: 11, fontSize: 13 },
  smsMessage: { minHeight: 100, maxHeight: 180 }, smsCount: { color: '#8FA9BD', fontSize: 10, textAlign: 'right' },
  loader: { marginTop: 16 }, footer: { color: '#71899E', fontSize: 10, lineHeight: 16, marginTop: 20 },
});
