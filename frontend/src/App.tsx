import React, { useState } from 'react';

export default function App() {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState<string | null>(null);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setResponse(`[V2 Agentic Response for: "${query}"]\nPowered by Kimi K2.6 (Supervisor), MiniMax M3 (Domain Specialist), and DeepSeek V4 Pro (Grounded RAG).`);
  };

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: '40px', maxWidth: '800px', margin: '0 auto' }}>
      <h1 style={{ color: '#1E88E5' }}>Axiom Tech Corporate AI Agent V2</h1>
      <p style={{ color: '#666' }}>Multi-Agent RAG System powered by NVIDIA NIM (Kimi K2.6, MiniMax M3, DeepSeek V4 Pro)</p>
      
      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
        <input 
          type="text" 
          value={query} 
          onChange={(e) => setQuery(e.target.value)} 
          placeholder="Ask about SEV incidents, home office policy, LGPD..." 
          style={{ flex: 1, padding: '12px', borderRadius: '6px', border: '1px solid #ccc', fontSize: '1rem' }} 
        />
        <button type="submit" style={{ padding: '12px 24px', backgroundColor: '#1E88E5', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}>
          Search
        </button>
      </form>

      {response && (
        <div style={{ marginTop: '30px', padding: '20px', backgroundColor: '#F5F5F5', borderRadius: '8px', borderLeft: '4px solid #1E88E5' }}>
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{response}</pre>
        </div>
      )}
    </div>
  );
}
