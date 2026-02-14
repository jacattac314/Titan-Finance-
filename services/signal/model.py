import torch
import torch.nn as nn
import logging

logger = logging.getLogger("TitanModel")

class HybridModel(nn.Module):
    def __init__(self, input_dim, hidden_dim=64, num_layers=2, num_classes=3):
        super(HybridModel, self).__init__()
        
        # 1. LSTM Branch (Temporal Dependencies)
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2)
        
        # 2. CNN Branch (Local Pattern Extraction)
        # Input: (Batch, Features, Seq_Len)
        self.cnn = nn.Sequential(
            nn.Conv1d(in_channels=input_dim, out_channels=32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.BatchNorm1d(32),
            nn.Conv1d(in_channels=32, out_channels=64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveMaxPool1d(1) # Output: (Batch, 64, 1) -> Flatten to (Batch, 64)
        )
        
        # 3. Transformer Encoder (Global Context / Attention)
        # Input: (Batch, Seq_Len, Features) (requires projecting features to d_model)
        self.embedding = nn.Linear(input_dim, hidden_dim)
        encoder_layer = nn.TransformerEncoderLayer(d_model=hidden_dim, nhead=4, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
        
        # Fusion Layer
        # Concatenate: LSTM_last_hidden (hidden_dim) + CNN_out (64) + Transformer_pool (hidden_dim)
        fusion_dim = hidden_dim + 64 + hidden_dim
        
        self.classifier = nn.Sequential(
            nn.Linear(fusion_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes), # [Buy, Hold, Sell]
            nn.Softmax(dim=1)
        )

    def forward(self, x):
        # x shape: (Batch, Seq_Len, Features)
        
        # --- LSTM Pass ---
        lstm_out, (h_n, c_n) = self.lstm(x)
        lstm_feat = h_n[-1] # Last hidden state: (Batch, Hidden_Dim)
        
        # --- CNN Pass ---
        # Permute for CNN: (Batch, Features, Seq_Len)
        x_cnn = x.permute(0, 2, 1)
        cnn_feat = self.cnn(x_cnn).squeeze(-1) # (Batch, 64)
        
        # --- Transformer Pass ---
        x_emb = self.embedding(x) # (Batch, Seq, Hidden)
        trans_out = self.transformer(x_emb)
        # Global Average Pooling for Transformer output
        trans_feat = torch.mean(trans_out, dim=1) # (Batch, Hidden)
        
        # --- Fusion ---
        combined = torch.cat((lstm_feat, cnn_feat, trans_feat), dim=1)
        logits = self.classifier(combined)
        
        return logits

def load_model(path: str = None, input_dim: int = 8):
    model = HybridModel(input_dim=input_dim)
    if path:
        try:
            model.load_state_dict(torch.load(path))
            logger.info(f"Loaded model weights from {path}")
        except Exception as e:
            logger.error(f"Failed to load model from {path}: {e}")
    else:
        logger.info("Initialized new HybridModel with random weights.")
    
    model.eval()
    return model
