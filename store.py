"""Persistence: Supabase (PostgREST over HTTPS) in production, JSON files for local testing."""
import json
import os
import re

import requests


class LocalStore:
    def __init__(self, root='data'):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _f(self, user, name):
        return os.path.join(self.root, f"{re.sub(r'[^a-z0-9_-]', '_', user.lower())}_{name}.json")

    def _read(self, user, name, default):
        try:
            with open(self._f(user, name), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _write(self, user, name, data):
        with open(self._f(user, name), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def load_profile(self, user):
        return self._read(user, 'profile', None)

    def save_profile(self, user, data):
        self._write(user, 'profile', data)

    def list_history(self, user):
        return sorted(self._read(user, 'history', []), key=lambda r: r['id'], reverse=True)

    def add_history(self, user, row):
        rows = self._read(user, 'history', [])
        row['id'] = max([r['id'] for r in rows], default=0) + 1
        rows.append(row)
        self._write(user, 'history', rows)

    def update_status(self, user, rid, status):
        rows = self._read(user, 'history', [])
        for r in rows:
            if r['id'] == rid:
                r['status'] = status
        self._write(user, 'history', rows)

    def delete_history(self, user, rid):
        self._write(user, 'history', [r for r in self._read(user, 'history', []) if r['id'] != rid])

    def get_usage(self, user, day):
        return self._read(user, 'usage', {}).get(day, 0)

    def inc_usage(self, user, day):
        u = self._read(user, 'usage', {})
        u[day] = u.get(day, 0) + 1
        self._write(user, 'usage', u)


class SupabaseStore:
    def __init__(self, url, key):
        self.base = url.rstrip('/') + '/rest/v1'
        self.h = {'apikey': key, 'Content-Type': 'application/json'}
        if not key.startswith('sb_'):  # legacy JWT keys also go in the Authorization header
            self.h['Authorization'] = f'Bearer {key}'

    def _req(self, method, path, **kw):
        r = requests.request(method, self.base + path, headers={**self.h, **kw.pop('headers', {})}, timeout=30, **kw)
        r.raise_for_status()
        return r.json() if r.content else None

    def load_profile(self, user):
        rows = self._req('GET', '/profiles', params={'username': f'eq.{user}', 'select': 'data'})
        return rows[0]['data'] if rows else None

    def save_profile(self, user, data):
        self._req('POST', '/profiles', params={'on_conflict': 'username'}, json={'username': user, 'data': data},
                  headers={'Prefer': 'resolution=merge-duplicates,return=minimal'})

    def list_history(self, user):
        return self._req('GET', '/history', params={'username': f'eq.{user}', 'order': 'created_at.desc'}) or []

    def add_history(self, user, row):
        self._req('POST', '/history', json={**row, 'username': user}, headers={'Prefer': 'return=minimal'})

    def update_status(self, user, rid, status):
        self._req('PATCH', '/history', params={'id': f'eq.{rid}', 'username': f'eq.{user}'}, json={'status': status})

    def delete_history(self, user, rid):
        self._req('DELETE', '/history', params={'id': f'eq.{rid}', 'username': f'eq.{user}'})

    def get_usage(self, user, day):
        rows = self._req('GET', '/ai_usage', params={'username': f'eq.{user}', 'day': f'eq.{day}', 'select': 'count'})
        return rows[0]['count'] if rows else 0

    def inc_usage(self, user, day):
        n = self.get_usage(user, day) + 1
        self._req('POST', '/ai_usage', params={'on_conflict': 'username,day'}, json={'username': user, 'day': day, 'count': n},
                  headers={'Prefer': 'resolution=merge-duplicates,return=minimal'})


def get_store(secrets):
    if secrets.get('SUPABASE_URL') and secrets.get('SUPABASE_KEY'):
        return SupabaseStore(secrets['SUPABASE_URL'], secrets['SUPABASE_KEY'])
    return LocalStore()
