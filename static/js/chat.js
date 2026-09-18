document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('ai-chat-toggle');
  const chatWindow = document.getElementById('ai-chat-window');
  const closeBtn = document.getElementById('ai-chat-close');
  const chatForm = document.getElementById('ai-chat-form');
  const chatInput = document.getElementById('ai-chat-input');
  const messagesContainer = document.getElementById('ai-chat-messages');
  
  if (!toggleBtn) return;

  // Toggle chat window
  toggleBtn.addEventListener('click', () => {
    const isHidden = chatWindow.hasAttribute('hidden');
    if (isHidden) {
      chatWindow.removeAttribute('hidden');
      chatInput.focus();
    } else {
      chatWindow.setAttribute('hidden', '');
    }
  });

  closeBtn.addEventListener('click', () => {
    chatWindow.setAttribute('hidden', '');
  });

  function addMessage(text, isUser = false) {
    const div = document.createElement('div');
    div.className = isUser ? 'user-message' : 'ai-message';
    div.innerHTML = text; // allow HTML for movie links
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function addTypingIndicator() {
    const div = document.createElement('div');
    div.className = 'typing-indicator';
    div.id = 'ai-typing';
    div.innerHTML = '<span></span><span></span><span></span>';
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function removeTypingIndicator() {
    const indicator = document.getElementById('ai-typing');
    if (indicator) indicator.remove();
  }

  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = chatInput.value.trim();
    if (!query) return;

    // 1. Add user message
    addMessage(query, true);
    chatInput.value = '';
    
    // 2. Add typing indicator
    addTypingIndicator();

    // 3. Send to backend
    try {
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
      const response = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ query: query })
      });

      const data = await response.json();
      removeTypingIndicator();
      
      if (data.error) {
        addMessage('Oops! Something went wrong: ' + data.error);
      } else {
        addMessage(data.reply);
      }
    } catch (err) {
      removeTypingIndicator();
      addMessage('Sorry, I could not connect to the server right now.');
    }
  });
});
