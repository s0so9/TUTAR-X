// Quick test script to verify backend API connectivity
// Run with: node test-api.js

const API_BASE_URL = 'http://127.0.0.1:8002/api/v1';

async function testAPI() {
  console.log('Testing API at:', API_BASE_URL);
  console.log('');

  // Calculate date range
  const today = new Date();
  const fromDate = formatDate(today);
  const futureDate = new Date(today);
  futureDate.setDate(futureDate.getDate() + 14);
  const toDate = formatDate(futureDate);

  const url = `${API_BASE_URL}/matches?from_date=${fromDate}&to_date=${toDate}&status=scheduled`;

  console.log('Request URL:', url);
  console.log('Date range:', fromDate, 'to', toDate);
  console.log('');

  try {
    const response = await fetch(url);
    console.log('Response status:', response.status);
    console.log('Response headers:', Object.fromEntries(response.headers.entries()));
    console.log('');

    if (!response.ok) {
      const text = await response.text();
      console.error('Error response body:', text);
      return;
    }

    const data = await response.json();
    console.log('Response data:');
    console.log('- count:', data.count);
    console.log('- matches.length:', data.matches?.length ?? 'undefined');
    console.log('- is_development_data:', data.is_development_data);
    console.log('');

    if (data.matches && data.matches.length > 0) {
      console.log('First match:');
      const match = data.matches[0];
      console.log(JSON.stringify(match, null, 2));
    } else {
      console.log('No matches returned!');
    }

  } catch (error) {
    console.error('Fetch error:', error.message);
    console.error('This usually means:');
    console.error('1. Backend is not running on port 8002');
    console.error('2. CORS is blocking the request');
    console.error('3. Network connectivity issue');
  }
}

function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

testAPI();
