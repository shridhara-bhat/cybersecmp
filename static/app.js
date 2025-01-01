document.addEventListener("DOMContentLoaded", () => {
    const forms = document.querySelectorAll("form");
    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const inputs = form.querySelectorAll("input, textarea");
            inputs.forEach((input) => {
                if (!input.value.trim()) {
                    alert("Please fill out all fields.");
                    event.preventDefault();
                }
            });
        });
    });
});
