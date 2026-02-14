import shap
import numpy as np
import torch
import logging

logger = logging.getLogger("TitanXAI")

class XAIEngine:
    def __init__(self, model, background_data):
        """
        Initialize SHAP Explainer.
        Args:
            model: PyTorch model (must have a forward method)
            background_data: Representative dataset (numpy array) for baseline (e.g., 100 samples)
        """
        self.model = model
        # DeepExplainer is suitable for Deep Learning models
        # We need to wrap the model to handle numpy inputs if necessary, 
        # but shap.DeepExplainer supports torch tensors directly.
        try:
            self.explainer = shap.DeepExplainer(model, torch.from_numpy(background_data).float())
            logger.info("SHAP DeepExplainer initialized.")
        except Exception as e:
            logger.warning(f"Failed to init SHAP (Normal during dev without real data): {e}")
            self.explainer = None

    def explain_prediction(self, input_tensor):
        """
        Generate SHAP values for a single prediction.
        Args:
            input_tensor: (1, Seq, Features)
        Returns:
            shap_values: List of numpy arrays (one for each output class)
        """
        if not self.explainer:
            return None

        # valid input check
        if isinstance(input_tensor, np.ndarray):
            input_tensor = torch.from_numpy(input_tensor).float()

        shap_values = self.explainer.shap_values(input_tensor)
        return shap_values

    def get_top_features(self, shap_values, feature_names, class_idx=0, top_k=3):
        """
        Extract the most influential features.
        """
        if not shap_values:
            return []

        # shap_values is a list [class_0_attribution, class_1_attribution, ...]
        # For the chosen class (e.g. Buy=0), get the attributions
        attrs = shap_values[class_idx] # Shape: (1, Seq, Features) OR (1, Features) depending on model
        
        # Aggregate over sequence if necessary (sum attribution over time)
        if len(attrs.shape) == 3:
            attrs = np.sum(attrs, axis=1) # (1, Features)
            
        attrs = attrs.flatten()
        
        # Get indices of top K features by absolute magnitude
        top_indices = np.argsort(np.abs(attrs))[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append({
                "feature": feature_names[idx] if idx < len(feature_names) else f"Feat_{idx}",
                "impact": float(attrs[idx])
            })
            
        return results
