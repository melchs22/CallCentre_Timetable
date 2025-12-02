// JavaScript for Timetable App
document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide messages after 5 seconds
    const messages = document.querySelectorAll('.message');
    messages.forEach(message => {
        setTimeout(() => {
            message.style.transition = 'opacity 0.5s ease';
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 500);
        }, 5000);
    });

    // Form validation enhancement
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let valid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    valid = false;
                    field.style.borderColor = '#dc3545';
                    
                    // Add error message if not exists
                    if (!field.nextElementSibling || !field.nextElementSibling.classList.contains('field-error')) {
                        const error = document.createElement('div');
                        error.className = 'field-error';
                        error.style.color = '#dc3545';
                        error.style.fontSize = '12px';
                        error.style.marginTop = '5px';
                        error.textContent = 'This field is required';
                        field.parentNode.appendChild(error);
                    }
                } else {
                    field.style.borderColor = '#ced4da';
                    const error = field.parentNode.querySelector('.field-error');
                    if (error) {
                        error.remove();
                    }
                }
            });

            if (!valid) {
                e.preventDefault();
                alert('Please fill in all required fields.');
            }
        });
    });

    // Date picker enhancement
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(input => {
        // Set min date to today for future dates
        if (!input.value) {
            const today = new Date().toISOString().split('T')[0];
            input.min = today;
        }
    });

    // Table row highlighting
    const tableRows = document.querySelectorAll('tbody tr');
    tableRows.forEach(row => {
        row.addEventListener('click', function() {
            this.style.backgroundColor = '#f8f9fa';
            setTimeout(() => {
                this.style.backgroundColor = '';
            }, 1000);
        });
    });

    // Auto-refresh for pending requests
    const pendingElements = document.querySelectorAll('.status-pending');
    if (pendingElements.length > 0) {
        setInterval(() => {
            // Check for updates every 30 seconds
            console.log('Checking for updates...');
            // In a real app, you might want to make an AJAX call here
        }, 30000);
    }

    // Print functionality
    const printButtons = document.querySelectorAll('.btn-print');
    printButtons.forEach(button => {
        button.addEventListener('click', function() {
            window.print();
        });
    });

    // Export functionality (placeholder)
    const exportButtons = document.querySelectorAll('.btn-export');
    exportButtons.forEach(button => {
        button.addEventListener('click', function() {
            alert('Export functionality would be implemented here.');
        });
    });
});

// Utility functions
function formatTime(timeString) {
    const time = new Date('1970-01-01T' + timeString + 'Z');
    return time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function calculateDuration(startTime, endTime) {
    const start = new Date('1970-01-01T' + startTime + 'Z');
    const end = new Date('1970-01-01T' + endTime + 'Z');
    const diff = (end - start) / (1000 * 60 * 60); // difference in hours
    return diff.toFixed(1) + ' hours';
}

// AJAX helper function
function makeRequest(url, method = 'GET', data = null) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open(method, url);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.setRequestHeader('Content-Type', 'application/json');
        
        xhr.onload = function() {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(JSON.parse(xhr.responseText));
            } else {
                reject(new Error('Request failed: ' + xhr.statusText));
            }
        };
        
        xhr.onerror = function() {
            reject(new Error('Network error'));
        };
        
        xhr.send(data ? JSON.stringify(data) : null);
    });
}