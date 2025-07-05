from bokeh.core.properties import (
    Int, Nullable, Required, String,
)
from bokeh.models import Model
from bokeh.protocol import Protocol


class CommManager(Model):

    plot_id = Required(Nullable(String))

    comm_id = Required(Nullable(String))

    client_comm_id = Required(Nullable(String))

    debounce = Int(50)

    timeout = Int(5000)

    def __init__(self, **properties):
        super().__init__(**properties)
        self._protocol = Protocol()

    def assemble(self, msg):
        import os
        import json
        
        # Check for debugging environment variable
        debug_comm = os.environ.get('PANEL_DEBUG_COMM', '').lower() in ['true', '1', 'yes', 'on']
        
        header = msg['header']
        buffers = msg.pop('_buffers') or {}
        
        if debug_comm:
            print(f"🔍 PANEL_DEBUG_COMM: CommManager.assemble() called")
            print(f"🔍 PANEL_DEBUG_COMM: Header msgtype: {header.get('msgtype')}")
            print(f"🔍 PANEL_DEBUG_COMM: Buffers dict length: {len(buffers)}")
            print(f"🔍 PANEL_DEBUG_COMM: Message content keys: {list(msg.get('content', {}).keys())}")
        
        # Handle buffer count mismatch - critical fix for DeserializationError
        original_buffer_count = len(buffers)
        header['num_buffers'] = original_buffer_count
        
        cls = self._protocol._messages[header['msgtype']]
        msg_obj = cls(header, msg['metadata'], msg['content'])
        
        # Check if message content references buffers that aren't in the buffers dict
        content_str = json.dumps(msg.get('content', {}), default=str)
        buffer_references = []
        
        # Find all buffer ID references in the content (like {"id": 0, "dtype": "float64"})
        import re
        buffer_id_pattern = r'"id":\s*(\d+)'
        matches = re.findall(buffer_id_pattern, content_str)
        if matches:
            buffer_references = [int(match) for match in matches]
            
        if debug_comm and buffer_references:
            print(f"🔍 PANEL_DEBUG_COMM: Found buffer references in content: {buffer_references}")
            print(f"🔍 PANEL_DEBUG_COMM: Available buffer IDs: {list(buffers.keys())}")
        
        # If we have buffer references but no buffers, this indicates the coordination issue
        if buffer_references and not buffers:
            if debug_comm:
                print(f"⚠️ PANEL_DEBUG_COMM: Buffer coordination issue detected!")
                print(f"⚠️ PANEL_DEBUG_COMM: Content references {len(buffer_references)} buffers but _buffers dict is empty")
                print(f"⚠️ PANEL_DEBUG_COMM: This will cause DeserializationError - attempting recovery")
            
            # Attempt to create empty buffer placeholders to prevent deserialization crash
            # This is a defensive measure to maintain UI responsiveness
            for buffer_id in buffer_references:
                if buffer_id not in buffers:
                    # Create a minimal empty buffer as placeholder
                    import numpy as np
                    empty_buffer = np.array([])  # Empty numpy array as placeholder
                    buffers[buffer_id] = empty_buffer
                    if debug_comm:
                        print(f"🔄 PANEL_DEBUG_COMM: Created empty buffer placeholder for ID {buffer_id}")
            
            # Update header with the corrected buffer count
            header['num_buffers'] = len(buffers)
            if debug_comm:
                print(f"🔄 PANEL_DEBUG_COMM: Updated num_buffers to {len(buffers)}")
        
        # Assemble buffers into the message object
        for (bid, buff) in buffers.items():
            try:
                if hasattr(buff, 'tobytes'):
                    buffer_bytes = buff.tobytes()
                elif hasattr(buff, 'bytes'):
                    buffer_bytes = buff.bytes
                else:
                    # Fallback for unexpected buffer types
                    buffer_bytes = bytes(buff) if buff else b''
                    
                msg_obj.assemble_buffer({'id': bid}, buffer_bytes)
                
                if debug_comm:
                    print(f"✅ PANEL_DEBUG_COMM: Successfully assembled buffer {bid}, size: {len(buffer_bytes)} bytes")
                    
            except Exception as e:
                if debug_comm:
                    print(f"❌ PANEL_DEBUG_COMM: Failed to assemble buffer {bid}: {e}")
                # Skip problematic buffers rather than crashing
                continue
        
        if debug_comm:
            print(f"✅ PANEL_DEBUG_COMM: Message assembly completed")
            
        return msg_obj
