const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const path = require('path');
const { GoogleGenAI } = require('@google/genai');

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' })); // Allow large image payloads
const PORT = 5000;

// Initialize Google Gemini AI (Make sure GEMINI_API_KEY is set in your environment variables)
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || "YOUR_GEMINI_API_KEY" });

// Initialize SQLite Database File
const dbFile = path.join(__dirname, 'agritech.db');
const db = new sqlite3.Database(dbFile, (err) => {
  if (err) console.error('Database connection error:', err.message);
  else console.log('✅ Connected to SQLite Database (agritech.db)');
});

// Create Tables if they don't exist
db.serialize(() => {
  db.run(`CREATE TABLE IF NOT EXISTS market (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, category TEXT, mode TEXT, price REAL,
    currentBid REAL, quantity TEXT, seller TEXT, phone TEXT, location TEXT, image TEXT
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS machinery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, type TEXT, category TEXT, rate TEXT,
    owner TEXT, phone TEXT, location TEXT, specs TEXT
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, crop TEXT, status TEXT, diagnosis TEXT, confidence TEXT
  )`);

  // Insert default items if market is empty
  db.get("SELECT COUNT(*) as count FROM market", (err, row) => {
    if (row.count === 0) {
      db.run(`INSERT INTO market (name, category, mode, price, currentBid, quantity, seller, phone, location, image) VALUES 
      ('Organic Roma Tomatoes', 'Vegetables', 'auction', 28, 32, '450 kg', 'Ramesh Gowda', '+91 98450 11223', 'Mandya', 'https://images.unsplash.com/photo-1592924357228-91a4daadcfea?auto=format&fit=crop&w=600&q=80'),
      ('Premium Sona Masoori Rice', 'Grains', 'direct', 54, NULL, '1,200 kg', 'Basavaraj Patil', '+91 97312 44556', 'Raichur', 'https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=600&q=80')`);
    }
  });

  db.get("SELECT COUNT(*) as count FROM machinery", (err, row) => {
    if (row.count === 0) {
      db.run(`INSERT INTO machinery (title, type, category, rate, owner, phone, location, specs) VALUES 
      ('Mahindra 575 DI Tractor + Rotavator', 'available', 'Heavy Machinery', '₹850 / hour', 'Suresh Tractor', '+91 98801 33445', 'Hubballi', '45 HP with experienced driver'),
      ('5HP Solar Water Pump & Panel Kit', 'available', 'Smart Equipment', '₹450 / day', 'GreenSun', '+91 96112 55667', 'Belagavi', 'Portable solar panels included')`);
    }
  });
});

// --- API ROUTES ---

// 1. AI Plant Doctor Vision Analysis Route
app.post('/api/plant-doctor/analyze', async (req, res) => {
  try {
    const { imageBase64, mimeType } = req.body;
    if (!imageBase64) {
      return res.status(400).json({ error: "No image provided for analysis." });
    }

    // Call Gemini 2.5 Flash Vision Model to inspect leaf photo
    const response = await ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: [
        {
          inlineData: {
            data: imageBase64,
            mimeType: mimeType || 'image/jpeg'
          }
        },
        {
          text: `You are an expert AI Plant Pathologist and Agronomist. Analyze this plant/leaf image carefully. 
          Provide your response strictly in valid JSON format (no markdown code blocks, just raw JSON) with the following exact keys:
          - "crop": Name of the crop or plant detected.
          - "status": One of "Healthy", "Pre-Disease Warning", or "Active Disease Detected".
          - "badgeColor": "green", "amber", or "red".
          - "diagnosis": Name of the disease or deficiency with confidence score (e.g. "Early Blight - 96% Confidence").
          - "prevention": An array of 3 bullet point strings detailing immediate field action or pre-disease preventive steps.
          - "organicCure": Description of organic remedy/bio-pesticide.
          - "chemicalCure": Recommended chemical treatment with exact dosage guidelines.`
        }
      ]
    });

    let textResult = response.text.replace(/```json/g, '').replace(/```/g, '').trim();
    const diagnosticReport = JSON.parse(textResult);

    res.json({ report: diagnosticReport });
  } catch (error) {
    console.error("AI Analysis Error:", error);
    res.status(500).json({ error: "Failed to analyze image with AI Plant Doctor." });
  }
});

// 2. Get Market Listings
app.get('/api/market', (req, res) => {
  db.all("SELECT * FROM market ORDER BY id DESC", [], (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

// 3. Add Market Listing
app.post('/api/market', (req, res) => {
  const { name, category, mode, price, quantity, seller, phone, location } = req.body;
  const currentBid = mode === 'auction' ? Number(price) : null;
  const image = "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80";

  const sql = `INSERT INTO market (name, category, mode, price, currentBid, quantity, seller, phone, location, image) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`;
  db.run(sql, [name, category, mode, price, currentBid, quantity, seller, phone, location, image], function(err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ id: this.lastID, name, category, mode, price, currentBid, quantity, seller, phone, location, image });
  });
});

// 4. Delete Market Listing
app.delete('/api/market/:id', (req, res) => {
  db.run("DELETE FROM market WHERE id = ?", [req.params.id], function(err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ success: true, deletedID: req.params.id });
  });
});

// 5. Get Machinery Listings
app.get('/api/machinery', (req, res) => {
  db.all("SELECT * FROM machinery ORDER BY id DESC", [], (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

// 6. Add Machinery Listing
app.post('/api/machinery', (req, res) => {
  const { title, type, category, rate, owner, phone, location, specs } = req.body;
  const sql = `INSERT INTO machinery (title, type, category, rate, owner, phone, location, specs) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`;
  db.run(sql, [title, type, category, rate, owner, phone, location, specs], function(err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ id: this.lastID, title, type, category, rate, owner, phone, location, specs });
  });
});

// 7. Delete Machinery Listing
app.delete('/api/machinery/:id', (req, res) => {
  db.run("DELETE FROM machinery WHERE id = ?", [req.params.id], function(err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ success: true, deletedID: req.params.id });
  });
});

app.listen(PORT, () => {
  console.log(`🚀 Database Backend Server running on http://localhost:${PORT}`);
});